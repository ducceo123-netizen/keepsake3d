"""Boundaries required by the single-process, public Render demo."""
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from apps.api.main import create_app
from apps.api.service import Service

@pytest.fixture
def public_client(tmp_path,monkeypatch):
    web=tmp_path/'export';web.mkdir()
    (web/'index.html').write_text('<html>Home</html>')
    (web/'studio').mkdir();(web/'studio/index.html').write_text('<html>Studio</html>')
    (web/'.env').write_text('SHOULD_NEVER_BE_PUBLIC=secret')
    (web/'api').mkdir();(web/'api/secret.txt').write_text('not-an-api')
    monkeypatch.setenv('KEEPSAKE_DEPLOYMENT_MODE','public-demo')
    monkeypatch.setenv('KEEPSAKE_ALLOWED_ORIGIN','https://demo.example')
    monkeypatch.setenv('KEEPSAKE_STORAGE_MODE','ephemeral')
    monkeypatch.setenv('KEEPSAKE_WEB_DIR',str(web))
    monkeypatch.delenv('KEEPSAKE_OPERATOR_TOKEN',raising=False)
    with TestClient(create_app(tmp_path/'private'),base_url='https://demo.example') as client:
        yield client

def create(client):
    response=client.post('/api/v1/customization-sessions',json={})
    assert response.status_code==201,response.text
    session=response.json()
    return session['id'],{'Authorization':'Bearer '+session['token']}

def test_static_export_and_api_remain_separate(public_client):
    assert public_client.get('/').text=='<html>Home</html>'
    assert public_client.get('/studio/').text=='<html>Studio</html>'
    health=public_client.get('/api/v1/health')
    assert health.status_code==200
    assert health.json()['mode']=='public-demo'
    assert health.json()['storage']=='ephemeral'
    assert isinstance(health.json()['generation_available'],bool)
    assert "default-src 'none'" in health.headers['content-security-policy']
    assert "script-src 'self' 'unsafe-inline'" in public_client.get('/').headers['content-security-policy']
    for path in ['/.env','/%2Eenv','/api/secret.txt','/docs','/openapi.json','/nonexistent']:
        assert public_client.get(path).status_code==404,path

def test_public_origin_host_and_security_headers(public_client):
    assert public_client.get('/',headers={'Host':'attacker.example'}).status_code==400
    rejected=public_client.post('/api/v1/customization-sessions',json={},headers={'Origin':'https://attacker.example'})
    assert rejected.status_code==403
    approved=public_client.post('/api/v1/customization-sessions',json={},headers={'Origin':'https://demo.example'})
    assert approved.status_code==201
    assert approved.headers['access-control-allow-origin']=='https://demo.example'
    response=public_client.get('/api/v1/health',headers={'Origin':'http://localhost:3000'})
    assert 'access-control-allow-origin' not in response.headers
    assert response.headers['x-frame-options']=='DENY'
    assert response.headers['strict-transport-security']=='max-age=31536000'

def test_forwarded_ip_cannot_bypass_session_rate_limit(public_client):
    results=[public_client.post('/api/v1/customization-sessions',json={},headers={'X-Forwarded-For':f'198.51.100.{n}'}) for n in range(11)]
    assert results[-1].status_code==429

def test_storage_and_session_caps(public_client):
    svc=public_client.app.state.service
    svc.max_sessions=1
    sid,headers=create(public_client)
    assert public_client.post('/api/v1/customization-sessions',json={}).status_code==503
    svc.max_storage=0
    assert public_client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).status_code==503
    assert svc.status(sid)['photos']==[]

def test_global_build_cap_cannot_be_bypassed_by_new_session(public_client,monkeypatch):
    svc=public_client.app.state.service
    svc.max_builds_hour=1
    monkeypatch.setattr(svc.pool,'submit',lambda *args,**kwargs:None)
    for n,expected in [(1,202),(2,429)]:
        sid,headers=create(public_client)
        assert public_client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).status_code==201
        result=public_client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':f'public-build-{n}'},json={'consent':True})
        assert result.status_code==expected,result.text

def test_public_image_decode_shares_worker_memory_budget(public_client):
    svc=public_client.app.state.service
    sid,headers=create(public_client)
    svc.memory_capacity.acquire()
    try:
        assert public_client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).status_code==503
        assert public_client.get('/api/v1/health').status_code==200
    finally:
        svc.memory_capacity.release()
    assert public_client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).status_code==201

def test_large_reference_is_resized_before_private_storage(public_client):
    sid,headers=create(public_client)
    buffer=io.BytesIO();Image.new('RGB',(3000,1000)).save(buffer,'JPEG')
    response=public_client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,files={'file':('photo.jpg',buffer.getvalue(),'image/jpeg')})
    assert response.status_code==201,response.text
    assert response.json()['width']==2048
    assert response.json()['height']<=2048

def test_second_api_process_for_same_data_fails_closed(tmp_path):
    first=Service(tmp_path/'private')
    try:
        with pytest.raises(RuntimeError,match='exactly one API process'):
            Service(tmp_path/'private')
    finally:
        first.close()

def test_unsafe_public_config_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('KEEPSAKE_DEPLOYMENT_MODE','public-demo')
    monkeypatch.setenv('KEEPSAKE_ALLOWED_ORIGIN','*')
    with pytest.raises(ValueError,match='exact HTTP'):
        create_app(tmp_path/'private')
    monkeypatch.setenv('KEEPSAKE_ALLOWED_ORIGIN','https://demo.example')
    monkeypatch.setenv('KEEPSAKE_OPERATOR_TOKEN','too-short')
    with pytest.raises(ValueError,match='32 random characters'):
        create_app(tmp_path/'private')

def test_private_data_cannot_be_inside_static_export(tmp_path,monkeypatch):
    web=tmp_path/'web';web.mkdir();(web/'index.html').write_text('home')
    monkeypatch.setenv('KEEPSAKE_WEB_DIR',str(web))
    with pytest.raises(ValueError,match='separate directories'):
        create_app(web/'private')

def test_upload_authentication_precedes_multipart_parsing(public_client):
    sid,_=create(public_client)
    result=public_client.post(f'/api/v1/sessions/{sid}/photos',content=b'bad multipart',headers={'Content-Type':'multipart/form-data; boundary=broken'})
    assert result.status_code==404

def test_concurrent_upload_admission_is_bounded(public_client):
    sid,headers=create(public_client)
    slots=public_client.app.state.service.upload_request_capacity
    slots.acquire();slots.acquire()
    try:
        response=public_client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,content=b'')
        assert response.status_code==503
    finally:
        slots.release();slots.release()
