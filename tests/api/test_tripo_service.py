"""Private Tripo workflow tests. All provider HTTP is intercepted; no credits spent."""
import hashlib
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.tripo import TripoService
from workers.tripo.client import MODEL, MODEL_OPTIONS, TripoClient
from tests.api.test_tripo_client import pack_glb

CODE = 'test-private-generation-code'


class Provider:
    def __init__(self):
        self.requests = []
        self.mode = 'success'
        self.credits = 30
        self.download_entered = threading.Event()
        self.download_release = threading.Event()
        self.query_entered = threading.Event()
        self.query_release = threading.Event()
        self.model = pack_glb()

    def handle(self, request):
        self.requests.append((request.method, request.url.path))
        path = request.url.path
        if path == '/v3/files':
            assert b'filename="reference.png"' in request.read()
            return httpx.Response(200, json={'code': 0, 'data': {'file_token': 'file_fixture'}})
        if path == '/v3/generation/image-to-model':
            assert json.loads(request.read()) == {'input': 'file_fixture', **MODEL_OPTIONS}
            if self.mode == 'uncertain':
                raise httpx.ReadTimeout('simulated lost create response')
            if self.mode == 'rejected':
                return httpx.Response(403, json={'code': 2010})
            return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'task-fixture-' + str(self.creates)}})
        if path.startswith('/v3/tasks/'):
            if self.mode == 'blocked-query':
                self.query_entered.set()
                assert self.query_release.wait(5)
            if self.mode == 'status-offline':
                raise httpx.ConnectError('simulated status outage')
            status = 'running' if self.mode == 'running' else 'success'
            if self.mode == 'failed':
                status = 'failed'
            return httpx.Response(200, json={'code': 0, 'data': {
                'task_id': path.rsplit('/', 1)[1], 'status': status, 'progress': 70,
                'credits_consumed': self.credits,
                'output': {'model_url': 'https://cdn.tripo3d.ai/test/model.glb?private=not-in-public-output'},
            }})
        assert request.url.host == '93.184.216.34'
        assert 'authorization' not in request.headers
        if self.mode == 'download-offline':
            raise httpx.ConnectError('simulated download outage')
        if self.mode == 'invalid-model':
            return httpx.Response(200, content=b'not a valid GLB')
        if self.mode == 'blocked-download':
            self.download_entered.set()
            assert self.download_release.wait(5)
        return httpx.Response(200, content=self.model)

    @property
    def creates(self):
        return sum(path == '/v3/generation/image-to-model' for _, path in self.requests)

    def client(self, api_key=None):
        return TripoClient(api_key or 'test-key', transport=httpx.MockTransport(self.handle), resolver=lambda host: ['93.184.216.34'])


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('KEEPSAKE_DEPLOYMENT_MODE', 'local-demo')
    monkeypatch.setenv('TRIPO_API_KEY', 'test-key')
    monkeypatch.setenv('TRIPO_GENERATION_CODE', CODE)
    monkeypatch.delenv('TRIPO_STATE_DIR', raising=False)
    monkeypatch.delenv('KEEPSAKE_WEB_DIR', raising=False)
    provider = Provider()
    monkeypatch.setattr('apps.api.tripo.TripoClient', provider.client)
    return tmp_path / 'private', provider


@pytest.fixture
def client(setup):
    root, provider = setup
    with TestClient(create_app(root)) as http:
        http.app.state.tripo.poll_interval = .005
        http.app.state.tripo.poll_window = .08
        yield http, provider


def session(http):
    created = http.post('/api/v1/customization-sessions', json={}).json()
    sid = created['id']
    headers = {'Authorization': 'Bearer ' + created['token']}
    photo = http.post(f'/api/v1/sessions/{sid}/fixture', headers=headers).json()
    return sid, headers, photo


def plan(http, sid, headers, photo):
    response = http.post(f'/api/v1/sessions/{sid}/tripo/plan', headers=headers,
                         json={'photo_id': photo['id'], 'photo_sha256': photo['sha256']})
    assert response.status_code == 201, response.text
    return response.json()


def submit(http, sid, headers, quote, key='tripo-first-attempt', **changes):
    body = {'plan_id': quote['id'], 'consent': True, 'cost_accepted': True, 'access_code': CODE, **changes}
    return http.post(f'/api/v1/sessions/{sid}/tripo/submit', headers={**headers, 'Idempotency-Key': key}, json=body)


def status(http, sid, headers):
    return http.get(f'/api/v1/sessions/{sid}/tripo/status', headers=headers).json()


def wait_state(http, sid, headers, expected):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        current = status(http, sid, headers)
        if current['state'] == expected:
            return current
        time.sleep(.01)
    raise AssertionError(current)


def test_disabled_config_is_honest_and_no_provider_traffic(setup, monkeypatch):
    root, provider = setup
    monkeypatch.delenv('TRIPO_API_KEY')
    with TestClient(create_app(root)) as http:
        config = http.get('/api/v1/tripo/config').json()
        assert not config['configured'] and not config['available']
        assert config['requires_access_code'] and config['estimated_credits'] == 30
        sid, headers, photo = session(http)
        assert http.post(f'/api/v1/sessions/{sid}/tripo/plan', headers=headers, json={'photo_id': photo['id'], 'photo_sha256': photo['sha256']}).status_code == 503
    assert provider.requests == []


def test_public_ephemeral_sessions_cannot_enable_paid_generation(client, monkeypatch):
    http, provider = client
    svc = http.app.state.tripo
    svc.sessions.public = True
    svc.close()
    monkeypatch.setenv('TRIPO_DURABLE_STATE', '1')
    monkeypatch.setenv('TRIPO_STATE_DIR', str(svc.sessions.root / 'claimed-durable'))
    monkeypatch.setenv('KEEPSAKE_STORAGE_MODE', 'ephemeral')
    http.app.state.tripo = TripoService(svc.sessions, provider.client())
    config = http.get('/api/v1/tripo/config').json()
    assert config['configured'] and not config['available']
    assert 'sessions, photos' in config['reason']
    assert provider.requests == []


def test_plan_owner_hash_expiry_and_no_external_transfer(client):
    http, provider = client
    sid, headers, photo = session(http)
    other, other_headers, _ = session(http)
    path = f'/api/v1/sessions/{sid}/tripo/plan'
    body = {'photo_id': photo['id'], 'photo_sha256': photo['sha256']}
    assert http.post(path, json=body).status_code == 404
    assert http.post(path, headers=other_headers, json=body).status_code == 404
    assert http.post(f'/api/v1/sessions/{other}/tripo/plan', headers=other_headers, json=body).status_code == 422
    assert http.post(path, headers=headers, json={**body, 'photo_sha256': '0' * 64}).status_code == 422
    first = plan(http, sid, headers, photo)
    assert plan(http, sid, headers, photo) == first
    assert first['model'] == MODEL and first['options'] == MODEL_OPTIONS
    assert provider.requests == []
    svc = http.app.state.tripo
    svc.db.execute('UPDATE plans SET expires_at=? WHERE id=?', ('2000-01-01', first['id'])); svc.db.commit()
    assert submit(http, sid, headers, first).status_code == 409
    assert provider.requests == []


@pytest.mark.parametrize('change,code', [({'consent': False}, 422), ({'cost_accepted': False}, 422), ({'cost_accepted': 1}, 422), ({'access_code': 'wrong-code'}, 403)])
def test_explicit_consent_cost_and_code_precede_reservation(client, change, code):
    http, provider = client
    sid, headers, photo = session(http)
    quote = plan(http, sid, headers, photo)
    assert submit(http, sid, headers, quote, **change).status_code == code
    assert status(http, sid, headers)['state'] == 'NOT_STARTED'
    assert http.app.state.tripo.db.execute('SELECT COUNT(*) FROM spend_ledger').fetchone()[0] == 0
    assert provider.requests == []


def test_real_client_mocked_workflow_private_artifacts_and_idempotency(client):
    http, provider = client
    sid, headers, photo = session(http)
    quote = plan(http, sid, headers, photo)
    assert submit(http, sid, headers, quote).status_code == 202
    ready = wait_state(http, sid, headers, 'READY')
    assert ready['credits_consumed'] == 30 and ready['progress'] == 100
    assert {a['kind'] for a in ready['artifacts']} == {'glb', 'provenance'}
    assert 'private=not-in-public-output' not in json.dumps(ready)
    assert CODE not in json.dumps(ready) and 'test-key' not in json.dumps(ready)
    assert submit(http, sid, headers, quote).json()['job_id'] == ready['job_id']
    assert submit(http, sid, headers, quote, key='different-key-same-plan').json()['job_id'] == ready['job_id']
    assert provider.creates == 1
    for artifact in ready['artifacts']:
        assert http.get(artifact['url']).status_code == 404
        response = http.get(artifact['url'], headers=headers)
        assert response.headers['cache-control'] == 'no-store'
        assert hashlib.sha256(response.content).hexdigest() == artifact['sha256']
        if artifact['kind'] == 'glb':
            assert response.content == provider.model
        else:
            assert response.json()['external_transfer'] is True
            assert response.json()['locked_design_geometry'] is False
    # Local Blender parameters and revision history remain untouched.
    local = http.get(f'/api/v1/sessions/{sid}/status', headers=headers).json()
    assert local['revision'] == 0 and local['params'] is None


def test_lost_create_response_is_never_repeated_even_after_restart(setup):
    root, provider = setup
    provider.mode = 'uncertain'
    with TestClient(create_app(root)) as http:
        sid, headers, photo = session(http)
        quote = plan(http, sid, headers, photo)
        assert submit(http, sid, headers, quote).status_code == 202
        uncertain = wait_state(http, sid, headers, 'SUBMISSION_UNCERTAIN')
        assert uncertain['error']['code'] == 'TRIPO_SUBMISSION_UNCERTAIN'
        assert submit(http, sid, headers, quote, key='retry-lost-response').status_code == 202
    with TestClient(create_app(root)) as http:
        assert status(http, sid, headers)['state'] == 'SUBMISSION_UNCERTAIN'
        assert submit(http, sid, headers, quote).status_code == 202
    assert provider.creates == 1


def test_known_remote_id_resumes_after_restart_without_recreation(setup):
    root, provider = setup
    provider.mode = 'running'
    with TestClient(create_app(root)) as http:
        http.app.state.tripo.poll_interval = .005
        http.app.state.tripo.poll_window = .03
        sid, headers, photo = session(http)
        assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
        pending = wait_state(http, sid, headers, 'WAITING_FOR_PROVIDER')
        task_id = pending['provider_task_id']
    provider.mode = 'success'
    with TestClient(create_app(root)) as http:
        ready = wait_state(http, sid, headers, 'READY')
        assert ready['provider_task_id'] == task_id
    assert provider.creates == 1


def test_restart_at_submission_boundary_never_sends_create_again(setup, monkeypatch):
    root, provider = setup
    with TestClient(create_app(root)) as http:
        svc = http.app.state.tripo
        monkeypatch.setattr(svc, '_schedule', lambda job: None)
        sid, headers, photo = session(http)
        assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
        svc.db.execute("UPDATE jobs SET state='SUBMITTING',provider_file_token='file_fixture'"); svc.db.commit()
    with TestClient(create_app(root)) as http:
        assert status(http, sid, headers)['state'] == 'SUBMISSION_UNCERTAIN'
    assert provider.creates == 0


def test_restart_cannot_silently_change_quoted_generation_settings(setup, monkeypatch):
    root, provider = setup
    with TestClient(create_app(root)) as http:
        svc = http.app.state.tripo
        monkeypatch.setattr(svc, '_schedule', lambda job: None)
        sid, headers, photo = session(http)
        assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
        svc.db.execute("UPDATE jobs SET model='older-quoted-model'"); svc.db.commit()
    with TestClient(create_app(root)) as http:
        failed = wait_state(http, sid, headers, 'FAILED')
        assert failed['error']['code'] == 'TRIPO_PLAN_CHANGED'
    assert provider.requests == []


def test_one_active_generation_and_no_automatic_reroll(client):
    http, provider = client
    provider.mode = 'running'
    a, ha, pa = session(http); b, hb, pb = session(http)
    qa = plan(http, a, ha, pa); qb = plan(http, b, hb, pb)
    assert submit(http, a, ha, qa).status_code == 202
    wait_state(http, a, ha, 'WAITING_FOR_PROVIDER')
    assert submit(http, b, hb, qb).status_code == 503
    assert provider.creates == 1
    svc = http.app.state.tripo
    provider.mode = 'failed'
    svc.db.execute('UPDATE jobs SET next_poll_at=0'); svc.db.commit()
    failed = wait_state(http, a, ha, 'FAILED')
    assert failed['credits_consumed'] == 30
    assert svc.db.execute('SELECT outcome,credits_consumed FROM spend_ledger').fetchone()[:] == ('FAILED', 30)
    assert submit(http, a, ha, qa, key='new-key-failed').json()['state'] == 'FAILED'
    assert provider.creates == 1


def test_deletion_purges_files_but_keeps_hourly_budget(client):
    http, provider = client
    for _ in range(3):
        sid, headers, photo = session(http)
        assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
        ready = wait_state(http, sid, headers, 'READY')
        folder = http.app.state.tripo.root / 'artifacts' / ready['job_id']
        assert folder.exists()
        assert http.delete(f'/api/v1/sessions/{sid}', headers=headers).status_code == 204
        assert not folder.exists()
        assert http.get(ready['artifacts'][0]['url'], headers=headers).status_code == 404
    sid, headers, photo = session(http)
    assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 429
    assert http.app.state.tripo.db.execute('SELECT COUNT(*) FROM spend_ledger').fetchone()[0] == 3
    assert provider.creates == 3


def test_delete_during_download_cannot_recreate_private_artifacts(client):
    http, provider = client
    provider.mode = 'blocked-download'
    sid, headers, photo = session(http)
    assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
    assert provider.download_entered.wait(2)
    svc = http.app.state.tripo
    job = status(http, sid, headers)['job_id']
    assert http.delete(f'/api/v1/sessions/{sid}', headers=headers).status_code == 204
    provider.download_release.set()
    svc.futures[job].result(timeout=2)
    assert not (svc.root / 'artifacts' / job).exists()
    assert svc.db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 0
    assert svc.db.execute('SELECT COUNT(*) FROM spend_ledger').fetchone()[0] == 1


def test_provider_success_is_billed_even_when_model_is_rejected(client):
    http, provider = client
    provider.mode = 'invalid-model'
    sid, headers, photo = session(http)
    quote = plan(http, sid, headers, photo)
    assert submit(http, sid, headers, quote).status_code == 202
    failed = wait_state(http, sid, headers, 'FAILED')
    assert failed['credits_consumed'] == 30
    assert failed['error']['code'] == 'TRIPO_MODEL_NOT_ACCEPTED'
    assert 'paid generation' in failed['error']['message']
    assert failed['artifacts'] == []
    ledger = http.app.state.tripo.db.execute('SELECT * FROM spend_ledger').fetchone()
    assert ledger['outcome'] == 'SUCCESS' and ledger['credits_consumed'] == 30
    assert submit(http, sid, headers, quote, key='retry-invalid-model').json()['state'] == 'FAILED'
    assert provider.creates == 1


def test_transient_download_failure_records_cost_and_resumes_same_task(client):
    http, provider = client
    provider.mode = 'download-offline'
    sid, headers, photo = session(http)
    assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
    waiting = wait_state(http, sid, headers, 'WAITING_FOR_PROVIDER')
    assert waiting['credits_consumed'] == 30
    svc = http.app.state.tripo
    assert svc.db.execute('SELECT outcome FROM spend_ledger').fetchone()[0] == 'SUCCESS'
    provider.mode = 'success'
    provider.credits = None  # Optional billing data can be absent on a later read.
    svc.db.execute('UPDATE jobs SET next_poll_at=0'); svc.db.commit()
    assert wait_state(http, sid, headers, 'READY')['credits_consumed'] == 30
    assert provider.creates == 1


def test_deletion_during_status_query_never_starts_model_download(client):
    http, provider = client
    provider.mode = 'blocked-query'
    sid, headers, photo = session(http)
    assert submit(http, sid, headers, plan(http, sid, headers, photo)).status_code == 202
    assert provider.query_entered.wait(2)
    svc = http.app.state.tripo
    job = status(http, sid, headers)['job_id']
    assert http.delete(f'/api/v1/sessions/{sid}', headers=headers).status_code == 204
    provider.query_release.set()
    svc.futures[job].result(timeout=2)
    assert all(path != '/test/model.glb' for _, path in provider.requests)
    assert not (svc.root / 'artifacts' / job).exists()
    assert svc.db.execute('SELECT outcome,credits_consumed FROM spend_ledger').fetchone()[:] == ('SUCCESS', 30)
