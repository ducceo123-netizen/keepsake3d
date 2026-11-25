"""Opt-in real Blender test: KEEPSAKE_RUN_BLENDER_TESTS=1 python -m pytest tests/api/test_blender_integration.py -q"""
import hashlib
import os
import time
import pytest
from fastapi.testclient import TestClient
from apps.api.main import create_app
from tests.api.profile_helpers import save_profile

pytestmark=pytest.mark.skipif(os.environ.get('KEEPSAKE_RUN_BLENDER_TESTS')!='1',reason='Opt-in actual Blender integration; no mock artifacts')

def test_real_generation_approval_and_revision(tmp_path):
    with TestClient(create_app(tmp_path/'private')) as client:
        session=client.post('/api/v1/customization-sessions',json={}).json()
        sid=session['id']; headers={'Authorization':'Bearer '+session['token']}
        base=f'/api/v1/sessions/{sid}'
        assert client.post(base+'/fixture',headers=headers).status_code==201
        profile=save_profile(client,sid,headers)
        submit=client.post(base+'/submit',headers={**headers,'Idempotency-Key':'real-build-1'},json={'consent':True,'names':['Ada','Sam'],'appearance_profile_id':profile['id'],'appearance_profile_sha256':profile['sha256']})
        assert submit.status_code==202,submit.text
        def wait_ready():
            for _ in range(1200):
                status=client.get(base+'/status',headers=headers).json()
                if status['state'] in {'PREVIEW_READY','FAILED'}:
                    assert status['state']=='PREVIEW_READY',status.get('error')
                    return status
                time.sleep(.5)
            pytest.fail('Blender did not complete within ten minutes')
        status=wait_ready()
        assert status['qa']['passed'] is True
        assert status['production_approved'] is False
        for artifact in status['artifacts']:
            data=client.get(artifact['url'],headers=headers)
            assert data.status_code==200
            assert hashlib.sha256(data.content).hexdigest()==artifact['sha256']
            assert client.get(artifact['url']).status_code==404
        original_checksum=status['checksum']
        assert client.post(base+'/approve',headers=headers,json={'model_revision':1,'job_checksum':original_checksum}).json()['state']=='CUSTOMER_APPROVED'
        corrected=client.post(base+'/corrections',headers={**headers,'Idempotency-Key':'real-correction-2'},json={'characters':{'left':{'outfit_palette_id':'sage'},'right':{'glasses_asset_id':'round'}}})
        assert corrected.status_code==202,corrected.text
        assert client.post(base+'/approve',headers=headers,json={'model_revision':1,'job_checksum':original_checksum}).status_code==409
        status=wait_ready()
        assert status['revision']==2
        assert status['qa']['passed'] is True
        assert status['checksum']!=original_checksum
        assert client.delete(base,headers=headers).status_code==204
        assert not (tmp_path/'private'/sid).exists()
