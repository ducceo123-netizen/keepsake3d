"""Synthetic API contract payloads, not claims of running real browser inference."""
from packages.schemas.models import Parameters


def payload_for_photo(photo,params=None):
    parameters=params or Parameters().model_dump()
    assignment={'photo_id':photo['id'],'photo_sha256':photo['sha256'],'face_count':2}
    observation={'measurements':{'face_pixels':128.0,'yaw_proxy':0.02,'roll_degrees':0.0},'confidence':'medium','observed_fields':['face_morphs.face_width','hair_color_id'],'warnings':['Synthetic contract test observations; not real face inference.']}
    return {'source':'browser-mediapipe-v1','analysis_version':'1.0','consent':True,'reviewed':True,
        'assignments':{'left':{**assignment,'face_index':0,'box':[0.1,0.1,0.3,0.6]},'right':{**assignment,'face_index':1,'box':[0.6,0.1,0.3,0.6]}},
        'parameters':parameters,'observations':{'left':observation,'right':observation},'manual_overrides':{'characters':{}}}


def save_profile(client,sid,headers,params=None):
    status=client.get(f'/api/v1/sessions/{sid}/status',headers=headers).json()
    photo=status['photos'][0]
    response=client.post(f'/api/v1/sessions/{sid}/appearance-profile',headers=headers,json=payload_for_photo(photo,params))
    assert response.status_code==201,response.text
    return response.json()
