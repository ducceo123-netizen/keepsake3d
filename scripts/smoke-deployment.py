"""Technical pipeline smoke only; does not verify photo appearance analysis. No secrets logged."""
import argparse
import hashlib
import json
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base_url')
    parser.add_argument('--generate', action='store_true', help='Run real Blender generation and a correction')
    parser.add_argument('--timeout', type=int, default=1100, help='Maximum seconds per real build')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}):
        parser.error('Use HTTPS for hosted session credentials.')
    session = None

    def request(path, body=None, method=None, authenticated=True, expected=200, raw=False):
        headers = {}
        if session and authenticated:
            headers['Authorization'] = 'Bearer ' + session['token']
        if body is not None:
            headers['Content-Type'] = 'application/json'
            headers['Idempotency-Key'] = str(uuid.uuid4())
        data = json.dumps(body).encode() if body is not None else None
        req = Request(base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=120)
        except HTTPError as exc:
            response = exc
        with response:
            result = response.read()
            assert response.status == expected, f'{method or "GET"} {path}: HTTP {response.status}, expected {expected}'
            if raw or expected == 204:
                return result
            return json.loads(result)

    health = request('/api/v1/health')
    assert health['status'] == 'ok' and health['production_enabled'] is False
    assert health.get('appearance_provider') == 'browser-mediapipe-v1', 'Expected browser-local photo analysis configuration.'
    print('Health passed:', json.dumps(health), flush=True)
    print('Scope: explicit technical fixture pipeline; browser photo analysis is tested separately.', flush=True)
    for path in ('/', '/studio/', '/design-system/', '/admin/'):
        assert b'<html' in request(path, raw=True)
    for path in ('/.env', '/.data/private/app.sqlite', '/api/v1/unknown-route'):
        request(path, expected=404, raw=True)
    print('Static routes and private-path isolation passed.', flush=True)

    def wait_ready():
        deadline = time.monotonic() + args.timeout
        last = None
        while time.monotonic() < deadline:
            status = request(prefix + '/status')
            if status['state'] != last:
                print('Build state:', status['state'], flush=True)
                last = status['state']
            if status['state'] == 'PREVIEW_READY':
                return status
            if status['state'] in {'FAILED', 'CANCELLED', 'EXPIRED'}:
                raise AssertionError('Build failed: ' + json.dumps(status.get('error')))
            time.sleep(3)
        raise TimeoutError('Real build did not finish before the verification deadline.')

    try:
        session = request('/api/v1/customization-sessions', {}, expected=201)
        prefix = '/api/v1/sessions/' + session['id']
        request(prefix + '/fixture', {}, expected=201)
        status = request(prefix + '/status')
        assert len(status['photos']) == 1
        photo_path = status['photos'][0]['url']
        assert request(photo_path, raw=True).startswith(b'\x89PNG')
        request(photo_path, authenticated=False, expected=404, raw=True)
        print('Synthetic photo and owner authorization passed.', flush=True)
        if args.generate:
            assert health.get('generation_available', True), 'Blender is not available.'
            request(prefix + '/submit', {'consent': True, 'mode': 'technical-fixture', 'names': ['Alex', 'Jamie']}, expected=202)
            first = wait_ready()
            assert first['appearance']['source'] == 'technical-fixture' and first['appearance']['is_mock'] is True
            for artifact in first['artifacts']:
                blob = request(artifact['url'], raw=True)
                assert hashlib.sha256(blob).hexdigest() == artifact['sha256'], artifact['kind']
            approval = {'model_revision': first['revision'], 'job_checksum': first['checksum']}
            request(prefix + '/approve', approval)
            assert request(prefix + '/status')['state'] == 'CUSTOMER_APPROVED'
            request(prefix + '/corrections', {'characters': {'left': {'outfit_palette_id': 'sage'}}}, expected=202)
            second = wait_ready()
            assert second['revision'] == first['revision'] + 1 and second['checksum'] != first['checksum']
            for artifact in second['artifacts']:
                blob = request(artifact['url'], raw=True)
                assert hashlib.sha256(blob).hexdigest() == artifact['sha256'], artifact['kind']
            request(prefix + '/approve', approval, expected=409, raw=True)
            print('Two real revisions, artifact hashes, approval and stale-approval rejection passed.', flush=True)
    finally:
        if session:
            request('/api/v1/sessions/' + session['id'], method='DELETE', expected=204)
            print('Disposable verification session deleted.', flush=True)
    print('Deployment smoke checks passed.', flush=True)


if __name__ == '__main__':
    main()
