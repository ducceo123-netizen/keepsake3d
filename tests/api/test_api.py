import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from apps.api.main import create_app
from apps.api.service import canonical, digest
from packages.schemas.models import Parameters, assert_transition

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'private')) as client:
        yield client

def new(client):
    response=client.post('/api/v1/customization-sessions',json={})
    assert response.status_code==201,response.text
    session=response.json()
    return session['id'],{'Authorization':'Bearer '+session['token']},session

def fixture(client,sid,headers):
    response=client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers)
    assert response.status_code==201,response.text
    return response.json()

def no_build(client,monkeypatch):
    # Contract tests isolate queue dispatch; real Blender is integration-tested separately.
    monkeypatch.setattr(client.app.state.service.pool,'submit',lambda *args,**kwargs: None)

def ready(client,sid,revision=1):
    svc=client.app.state.service
    svc._advance(sid,'QA_RUNNING')
    if svc.get(sid)['state']=='PHOTO_VALIDATING':
        svc.transition(sid,'AI_ANALYZING');svc.transition(sid,'PARAMETERS_READY');svc._advance(sid,'QA_RUNNING')
    svc.transition(sid,'PREVIEW_READY')
    with svc.lock:
        svc.db.execute('UPDATE sessions SET checksum=? WHERE id=?',('a'*64,sid));svc.db.commit()

def submit(client,sid,headers,names=None,key='test-build-1'):
    return client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':key},json={'consent':True,'names':names or ['Ada','Sam']})

def test_health_is_explicit_demo(client):
    response=client.get('/api/v1/health')
    assert response.json()['production_enabled'] is False
    assert response.headers['cache-control']=='no-store'

def test_unknown_design_rejected(client):
    assert client.post('/api/v1/customization-sessions',json={'design_version':'production'}).status_code==422

def test_token_hash_and_private_auth(client):
    sid,headers,session=new(client)
    row=client.app.state.service.get(sid)
    assert session['token'] not in json.dumps(row)
    assert row['token_hash']==digest(session['token'].encode())
    assert client.get(f'/api/v1/sessions/{sid}/status').status_code==404
    assert client.get(f'/api/v1/sessions/{sid}/status',headers=headers).status_code==200

def test_cross_session_photo_and_status_isolation(client):
    sid,a,_=new(client);other,b,_=new(client)
    photo=fixture(client,sid,a)
    assert client.get(photo['url'],headers=b).status_code==404
    assert client.get(f'/api/v1/sessions/{sid}/status',headers=b).status_code==404
    assert client.get(f'/api/v1/sessions/{other}/photos/{photo["id"]}',headers=b).status_code==404
    response=client.get(photo['url'],headers=a)
    assert response.content.startswith(b'\x89PNG')
    assert response.headers['cache-control']=='no-store'

def test_signature_spoof_and_tiny_images_rejected(client):
    sid,headers,_=new(client)
    assert client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,files={'file':('fake.png',b'not-an-image','image/png')}).status_code==415
    buffer=io.BytesIO();Image.new('RGB',(12,12)).save(buffer,'PNG')
    assert client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,files={'file':('tiny.png',buffer.getvalue(),'image/png')}).status_code==422

def test_upload_count_and_removal(client):
    sid,headers,_=new(client)
    photos=[fixture(client,sid,headers) for _ in range(3)]
    assert client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).status_code==422
    for photo in photos:
        assert client.delete(photo['url'],headers=headers).status_code==204
    assert client.get(f'/api/v1/sessions/{sid}/status',headers=headers).json()['state']=='CREATED'

def test_exif_metadata_is_removed(client):
    sid,headers,_=new(client)
    buffer=io.BytesIO();img=Image.new('RGB',(128,128));exif=Image.Exif();exif[270]='PRIVATE LOCATION';img.save(buffer,'JPEG',exif=exif)
    response=client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,files={'file':('../../escape.jpg',buffer.getvalue(),'image/jpeg')})
    assert response.status_code==201
    stored=client.get(response.json()['url'],headers=headers).content
    with Image.open(io.BytesIO(stored)) as clean:
        assert not clean.getexif()
    assert b'PRIVATE LOCATION' not in stored
    assert not (client.app.state.service.root.parent/'escape.jpg').exists()

def test_consent_photo_and_names_validation(client):
    sid,headers,_=new(client)
    assert submit(client,sid,headers).status_code==409
    fixture(client,sid,headers)
    for payload in [{'consent':False,'names':['Ada','Sam']},{'consent':True,'names':['../../bad','Sam']},{'consent':True,'names':['Ada','Sam'],'shell':'whoami'}]:
        assert client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':'invalid-1'},json=payload).status_code==422
    assert client.post(f'/api/v1/sessions/{sid}/submit',headers=headers,json={'consent':True}).status_code==422

def test_submit_is_idempotent_and_payload_bound(client,monkeypatch):
    no_build(client,monkeypatch)
    sid,headers,_=new(client);fixture(client,sid,headers)
    first=submit(client,sid,headers);again=submit(client,sid,headers)
    assert first.status_code==again.status_code==202
    assert first.json()['job_id']==again.json()['job_id']
    assert first.json()['revision']==again.json()['revision']==1
    assert submit(client,sid,headers,['Different','Sam']).status_code==409
    assert client.app.state.service.db.execute('SELECT COUNT(*) FROM build_jobs').fetchone()[0]==1

def test_concurrent_idempotent_dispatch(client,monkeypatch):
    no_build(client,monkeypatch)
    sid,headers,_=new(client);fixture(client,sid,headers)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:submit(client,sid,headers),range(4)))
    assert {r.status_code for r in results}=={202}
    assert len({r.json()['job_id'] for r in results})==1

def test_revision_approval_and_corrections(client,monkeypatch):
    no_build(client,monkeypatch)
    sid,headers,_=new(client);fixture(client,sid,headers);submit(client,sid,headers)
    ready(client,sid)
    url=f'/api/v1/sessions/{sid}/approve'
    assert client.post(url,headers=headers,json={'model_revision':2,'job_checksum':'a'*64}).status_code==409
    approved=client.post(url,headers=headers,json={'model_revision':1,'job_checksum':'a'*64})
    assert approved.json()['state']=='CUSTOMER_APPROVED'
    assert approved.json()['production_approved'] is False
    correction=client.post(f'/api/v1/sessions/{sid}/corrections',headers={**headers,'Idempotency-Key':'correction-1'},json={'characters':{'left':{'outfit_palette_id':'sage'}}})
    assert correction.status_code==202,correction.text
    assert correction.json()['revision']==2
    assert correction.json()['checksum'] is None
    assert correction.json()['params']['characters']['left']['outfit_palette_id']=='sage'
    assert client.post(url,headers=headers,json={'model_revision':1,'job_checksum':'a'*64}).status_code==409

def test_unsupported_parameters_fail_closed(client):
    sid,headers,_=new(client)
    for field in [{'geometry':'resize'},{'face_morphs':{'nose':9}},{'skin_material_id':'inferred-race'}]:
        assert client.post(f'/api/v1/sessions/{sid}/corrections',headers=headers,json={'characters':{'left':field}}).status_code==422
    with pytest.raises(ValidationError):
        Parameters.model_validate({'characters':{'left':{'face_morphs':{'smile':0.5}},'right':{}}})

def test_invalid_state_transition_disallowed():
    with pytest.raises(ValueError):
        assert_transition('CREATED','CUSTOMER_APPROVED')
    with pytest.raises(ValueError):
        assert_transition('CUSTOMER_APPROVED','PRODUCTION_APPROVED')

def test_expired_session_purges_photos(client):
    sid,headers,_=new(client);fixture(client,sid,headers)
    svc=client.app.state.service
    with svc.lock:
        svc.db.execute('UPDATE sessions SET expires_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),sid));svc.db.commit()
    assert client.get(f'/api/v1/sessions/{sid}/status',headers=headers).status_code==410
    assert not (svc.root/sid).exists()
    assert svc.db.execute('SELECT COUNT(*) FROM photos').fetchone()[0]==0

def test_delete_is_owned_and_removes_files(client):
    sid,headers,_=new(client);_,other,_=new(client);fixture(client,sid,headers)
    assert client.delete(f'/api/v1/sessions/{sid}',headers=other).status_code==404
    assert client.delete(f'/api/v1/sessions/{sid}',headers=headers).status_code==204
    assert client.get(f'/api/v1/sessions/{sid}/status',headers=headers).status_code==404
    assert not (client.app.state.service.root/sid).exists()

def test_operator_endpoint_disabled_without_secret(client,monkeypatch):
    monkeypatch.delenv('KEEPSAKE_OPERATOR_TOKEN',raising=False)
    assert client.get('/api/v1/admin/jobs',headers={'Authorization':'Bearer guess'}).status_code==403
    monkeypatch.setenv('KEEPSAKE_OPERATOR_TOKEN','operator-test-secret')
    assert client.get('/api/v1/admin/jobs',headers={'Authorization':'Bearer operator-test-secret'}).status_code==200

def test_creation_rate_limit(client):
    results=[client.post('/api/v1/customization-sessions',json={}) for _ in range(11)]
    assert results[-1].status_code==429
    assert results[-1].headers['retry-after']=='60'

def test_strict_manifest_rejects_missing_locks():
    from packages.schemas.models import DemoManifest
    from apps.api.service import ROOT
    data=json.loads((ROOT/'assets/designs/better-together/0.1.0-demo/manifest.json').read_text())
    DemoManifest.model_validate(data)
    data['geometry_lock_objects'].remove('HEART_BASE_LEFT')
    with pytest.raises(ValidationError):
        DemoManifest.model_validate(data)

def test_provenance_tampering_and_absent_qa_do_not_pass(client,tmp_path):
    """Isolated fake bytes verify rejection only; never emitted as preview artifacts."""
    from apps.api.service import ROOT
    params=Parameters().model_dump()
    folder=tmp_path/'verification-fixture';folder.mkdir()
    (folder/'model.glb').write_bytes(b'glTF-not-a-real-model')
    (folder/'model.stl').write_bytes(b'not-a-real-stl')
    (folder/'preview.png').write_bytes(b'\x89PNG\r\n\x1a\n-not-a-real-image')
    qa={'result':'DEMO_GEOMETRY_CHECKED','print_approved':False}  # missing explicit pass must fail
    (folder/'qa.json').write_text(canonical(qa))
    manifest=json.loads((ROOT/'assets/designs/better-together/0.1.0-demo/manifest.json').read_text())
    provenance={'design_id':'better-together','design_version':'0.1.0-demo','model_revision':1,'master_sha256':manifest['master_sha256'],'params_sha256':digest(canonical(params).encode()),'same_scene_export':True,'status':'DEMO_NOT_PRINT_APPROVED'}
    provenance['artifacts']=[]
    for kind,name in [('glb','model.glb'),('stl','model.stl'),('png','preview.png'),('qa','qa.json')]:
        data=(folder/name).read_bytes()
        provenance['artifacts'].append({'kind':kind,'filename':name,'sha256':digest(data),'bytes':len(data),'model_revision':1,'params_sha256':provenance['params_sha256'],'master_sha256':manifest['master_sha256']})
    provenance['job_checksum']=digest(canonical(provenance).encode())
    (folder/'provenance.json').write_text(canonical(provenance))
    with pytest.raises(RuntimeError,match='QA_FAILED'):
        client.app.state.service._accept_artifacts('test','test',1,folder,params)
    (folder/'model.glb').write_bytes(b'glTF-tampered')
    with pytest.raises(RuntimeError,match='PROVENANCE_MISMATCH'):
        client.app.state.service._accept_artifacts('test','test',1,folder,params)

def test_artifacts_cannot_be_read_with_another_session_token(client):
    sid,headers,_=new(client);other,b,_=new(client)
    assert client.get(f'/api/v1/sessions/{sid}/artifacts/not-real',headers=b).status_code==404
    assert client.get(f'/api/v1/sessions/{sid}/artifacts/not-real',headers=headers).status_code==404

def test_retry_same_parameters_preserves_revision_but_changes_attempt(client,monkeypatch):
    no_build(client,monkeypatch)
    sid,headers,_=new(client);fixture(client,sid,headers)
    first=submit(client,sid,headers).json()
    svc=client.app.state.service;svc.transition(sid,'FAILED')
    retry=submit(client,sid,headers,key='retry-build-2')
    assert retry.status_code==202,retry.text
    assert retry.json()['revision']==first['revision']==1
    assert retry.json()['job_id']!=first['job_id']
    attempts=[row[0] for row in svc.db.execute('SELECT attempts FROM build_jobs ORDER BY created_at')]
    assert attempts==[1,2]

def test_request_size_rejected_before_multipart_parser(client):
    sid,headers,_=new(client)
    response=client.post(f'/api/v1/sessions/{sid}/photos',headers={**headers,'Content-Length':str(12*1024*1024)},content=b'')
    assert response.status_code==413

def test_deleting_session_terminates_worker_process_group(client,tmp_path):
    import subprocess
    import sys
    import time
    sid,headers,_=new(client)
    marker=tmp_path/'should-not-be-written'
    ready_marker=tmp_path/'child-started'
    child_code=f"import time;from pathlib import Path;Path({str(ready_marker)!r}).write_text('ready');time.sleep(1);Path({str(marker)!r}).write_text('orphan')"
    parent_code=f"import subprocess,sys;subprocess.run([sys.executable,'-c',{child_code!r}])"
    process=subprocess.Popen([sys.executable,'-c',parent_code],start_new_session=True)
    client.app.state.service.processes[sid]=process
    for _ in range(100):
        if ready_marker.exists():break
        time.sleep(.01)
    assert ready_marker.exists()
    assert client.delete(f'/api/v1/sessions/{sid}',headers=headers).status_code==204
    assert process.poll() is not None
    time.sleep(1.1)
    assert not marker.exists()
    client.app.state.service.processes.pop(sid,None)
