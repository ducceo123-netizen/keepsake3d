import copy
import hashlib
import io
import json
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from apps.api.main import create_app
from packages.schemas.models import Parameters
from tests.api.profile_helpers import payload_for_photo

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'private')) as client:
        yield client

def session(client):
    result=client.post('/api/v1/customization-sessions',json={}).json()
    sid=result['id'];headers={'Authorization':'Bearer '+result['token']}
    photo=client.post(f'/api/v1/sessions/{sid}/fixture',headers=headers).json()
    return sid,headers,photo

def store(client,sid,headers,payload):
    return client.post(f'/api/v1/sessions/{sid}/appearance-profile',headers=headers,json=payload)

def begin(client,sid,headers,profile,key='profile-build-1'):
    return client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':key},json={'consent':True,'appearance_profile_id':profile['id'],'appearance_profile_sha256':profile['sha256']})

def test_normal_submit_never_falls_back_to_mock(client):
    sid,headers,_=session(client)
    response=client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':'missing-profile'},json={'consent':True,'names':['Ada','Sam']})
    assert response.status_code==422
    assert client.app.state.service.db.execute('SELECT COUNT(*) FROM build_jobs').fetchone()[0]==0

def test_normalized_photo_hash_is_exposed_only_to_owner(client):
    sid,headers,photo=session(client)
    data=client.get(photo['url'],headers=headers).content
    assert hashlib.sha256(data).hexdigest()==photo['sha256']
    status=client.get(f'/api/v1/sessions/{sid}/status',headers=headers).json()
    assert status['photos'][0]['sha256']==photo['sha256']
    assert client.get(photo['url']).status_code==404

def test_profile_idempotence_is_durable_even_when_build_processing(client,monkeypatch):
    sid,headers,photo=session(client)
    payload=payload_for_photo(photo)
    first=store(client,sid,headers,payload).json()
    monkeypatch.setattr(client.app.state.service.pool,'submit',lambda *args,**kwargs:None)
    assert begin(client,sid,headers,first).status_code==202
    repeat=store(client,sid,headers,payload)
    assert repeat.status_code==201,repeat.text
    assert repeat.json()['id']==first['id']
    assert repeat.json()['sha256']==first['sha256']
    assert client.app.state.service.db.execute('SELECT COUNT(*) FROM appearance_profiles').fetchone()[0]==1

@pytest.mark.parametrize('mutation', ['no-face','duplicate-face','out-of-range-index','ambiguous-review','bad-box','tiny-face','changed-hash','missing-face','raw-landmarks','implicit-defaults','unbounded-morph','unknown-geometry','numeric-confidence'])
def test_bad_or_ambiguous_analysis_is_rejected(client,mutation):
    sid,headers,photo=session(client)
    payload=copy.deepcopy(payload_for_photo(photo))
    if mutation=='no-face':payload['assignments']['left']['face_count']=0
    elif mutation=='duplicate-face':payload['assignments']['right']=copy.deepcopy(payload['assignments']['left'])
    elif mutation=='out-of-range-index':payload['assignments']['left']['face_index']=2
    elif mutation=='ambiguous-review':payload['reviewed']=False
    elif mutation=='bad-box':payload['assignments']['left']['box']=[0.8,0.1,0.3,0.5]
    elif mutation=='tiny-face':payload['assignments']['left']['box']=[0.1,0.1,0.001,0.002]
    elif mutation=='changed-hash':payload['assignments']['left']['photo_sha256']='a'*64
    elif mutation=='missing-face':del payload['assignments']['right']
    elif mutation=='raw-landmarks':payload['observations']['left']['landmarks']=[1,2,3]
    elif mutation=='implicit-defaults':payload['parameters']['characters']['left'].pop('skin_material_id')
    elif mutation=='unbounded-morph':payload['parameters']['characters']['left']['face_morphs']['nose_width']=2
    elif mutation=='unknown-geometry':payload['parameters']['characters']['left']['body_scale']=2
    elif mutation=='numeric-confidence':payload['observations']['left']['confidence']=0.99
    response=store(client,sid,headers,payload)
    assert response.status_code==422,response.text
    assert client.app.state.service.db.execute('SELECT COUNT(*) FROM appearance_profiles').fetchone()[0]==0

def test_cross_session_photo_and_profile_binding(client):
    a,ha,photo_a=session(client);b,hb,photo_b=session(client)
    assert store(client,a,ha,payload_for_photo(photo_b)).status_code==422
    saved=store(client,a,ha,payload_for_photo(photo_a)).json()
    assert client.get(f'/api/v1/sessions/{b}/appearance-profile/{saved["id"]}',headers=hb).status_code==404
    assert begin(client,b,hb,saved).status_code==404

def test_observed_defaulted_and_manual_fields_remain_distinct(client):
    sid,headers,photo=session(client)
    payload=copy.deepcopy(payload_for_photo(photo))
    payload['parameters']['characters']['left']['glasses_asset_id']='rectangular'
    payload['manual_overrides']={'characters':{'left':{'glasses_asset_id':'rectangular'}}}
    profile=store(client,sid,headers,payload).json()
    left=profile['observations']['left']
    assert 'hair_color_id' in left['observed_fields']
    assert 'glasses_asset_id' in left['manual_fields']
    assert 'face_morphs.nose_projection' in left['defaulted_fields']
    assert 'glasses_asset_id' not in left['defaulted_fields']
    assert profile['external_transfer'] is False
    assert profile['consent_policy']=='browser-local-v1'

def test_manual_override_must_match_final_reviewed_parameters(client):
    sid,headers,photo=session(client)
    payload=copy.deepcopy(payload_for_photo(photo))
    payload['manual_overrides']={'characters':{'left':{'glasses_asset_id':'rectangular'}}}
    assert store(client,sid,headers,payload).status_code==422

def test_correction_creates_immutable_profile_and_preserves_other_morphs(client,monkeypatch):
    sid,headers,photo=session(client)
    params=Parameters().model_dump();params['characters']['left']['face_morphs']['face_width']=0.42
    first=store(client,sid,headers,payload_for_photo(photo,params)).json()
    svc=client.app.state.service;monkeypatch.setattr(svc.pool,'submit',lambda *args,**kwargs:None)
    assert begin(client,sid,headers,first).status_code==202
    svc._advance(sid,'QA_RUNNING');svc.transition(sid,'PREVIEW_READY')
    response=client.post(f'/api/v1/sessions/{sid}/corrections',headers={**headers,'Idempotency-Key':'change-nose-width'},json={'characters':{'left':{'face_morphs':{'nose_width':-0.3,'face_width':0.42},'pants_palette_id':'navy','skin_material_id':params['characters']['left']['skin_material_id']}}})
    assert response.status_code==202,response.text
    status=response.json();second=svc.appearance_profile(sid,status['appearance']['profile_id'])
    assert second['parent_id']==first['id'] and second['revision']==first['revision']+1
    assert second['sha256']!=first['sha256']
    assert second['parameters']['characters']['left']['face_morphs']['face_width']==0.42
    assert second['parameters']['characters']['left']['face_morphs']['nose_width']==-0.3
    assert second['manual_overrides']['characters']['left']=={'face_morphs':{'nose_width':-0.3},'pants_palette_id':'navy'}
    assert svc.appearance_profile(sid,first['id'])==first
    assert status['appearance']['is_mock'] is False
    assert status['appearance']['external_transfer'] is False
    assert svc.db.execute('SELECT appearance_profile_id FROM build_jobs WHERE id=?',(status['job_id'],)).fetchone()[0]==second['id']

def test_stale_or_tampered_profile_hash_blocks_generation(client):
    sid,headers,photo=session(client)
    profile=store(client,sid,headers,payload_for_photo(photo)).json()
    wrong={**profile,'sha256':'a'*64}
    assert begin(client,sid,headers,wrong).status_code==409
    corrupted=copy.deepcopy(profile);corrupted['parameters']['characters']['left']['hair_color_id']='silver'
    svc=client.app.state.service
    with svc.lock:
        svc.db.execute('UPDATE appearance_profiles SET payload_json=? WHERE id=?',(json.dumps(corrupted),profile['id']));svc.db.commit()
    assert begin(client,sid,headers,profile).status_code==409

def test_technical_fixture_cannot_process_uploaded_customer_image(client):
    sid,headers,_=session(client)
    image=io.BytesIO();Image.new('RGB',(128,128)).save(image,'PNG')
    assert client.post(f'/api/v1/sessions/{sid}/photos',headers=headers,files={'file':('upload.png',image.getvalue(),'image/png')}).status_code==201
    result=client.post(f'/api/v1/sessions/{sid}/submit',headers={**headers,'Idempotency-Key':'technical-misuse'},json={'consent':True,'mode':'technical-fixture'})
    assert result.status_code==422

def test_delete_session_purges_derived_appearance_data(client):
    sid,headers,photo=session(client)
    assert store(client,sid,headers,payload_for_photo(photo)).status_code==201
    assert client.delete(f'/api/v1/sessions/{sid}',headers=headers).status_code==204
    assert client.app.state.service.db.execute('SELECT COUNT(*) FROM appearance_profiles').fetchone()[0]==0
