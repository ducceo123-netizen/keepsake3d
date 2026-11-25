"""Contract, topology, immutable-master and real-artifact regression checks."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys

import numpy as np
import pytest
import trimesh

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from packages.schemas.constants import DESIGN_VERSION,FACE_MORPH_KEYS
from workers.blender.run import validate_params,verify_manifest,validate_appearance
from workers.blender.morphs import deform_head_point,neutral_morphs,srgb_to_linear_hex
from workers.qa.geometry import inspect_topology
DESIGN=ROOT/'assets/designs/better-together'/DESIGN_VERSION

@pytest.fixture
def params():return json.loads((DESIGN/'example-params.json').read_text())

def test_valid_params_and_rejected_unknown_fields(params):
    assert validate_params(params)==params
    params['characters']['left']['python']='print(1)'
    with pytest.raises(ValueError,match='unknown'):validate_params(params)

@pytest.mark.parametrize('field,value',[('hair_style_asset_id','freeform'),('skin_material_id','unsupported'),('pants_palette_id','unknown'),('engraving_text','../../private'),('engraving_text','A'*13)])
def test_unsupported_edits_rejected(params,field,value):
    params['characters']['right'][field]=value
    with pytest.raises(ValueError):validate_params(params)

@pytest.mark.parametrize('value',[1.001,-1.001,float('nan'),float('inf'),True,'0.5'])
def test_out_of_range_nonfinite_and_wrong_type_morphs_rejected(params,value):
    params['characters']['left']['face_morphs']['jaw_width']=value
    with pytest.raises(ValueError):validate_params(params)

def test_missing_and_extra_morph_controls_rejected(params):
    del params['characters']['left']['face_morphs']['chin_length']
    with pytest.raises(ValueError,match='exactly'):validate_params(params)
    params['characters']['left']['face_morphs']['freeform_mesh']=0.0
    with pytest.raises(ValueError,match='exactly'):validate_params(params)

def test_manifest_integrity_and_required_locks():
    manifest=json.loads((DESIGN/'manifest.json').read_text())
    assert verify_manifest(manifest).suffix=='.blend'
    tampered=copy.deepcopy(manifest);tampered['master_sha256']='0'*64
    with pytest.raises(ValueError,match='SHA256'):verify_manifest(tampered)
    missing=copy.deepcopy(manifest);missing['geometry_lock_objects']=[]
    with pytest.raises(ValueError,match='locked geometry'):verify_manifest(missing)
    unknown=copy.deepcopy(manifest);unknown['allowed_shape_keys']['unapproved']={'min':-1.0,'max':1.0,'default':0.0}
    with pytest.raises(ValueError,match='authored'):verify_manifest(unknown)

def test_master_upgrade_preserves_every_legacy_lock_and_old_master_bytes():
    old=ROOT/'assets/designs/better-together/0.1.0-demo'
    old_manifest=json.loads((old/'manifest.json').read_text())
    report=json.loads((DESIGN/'master-upgrade-report.json').read_text())
    assert hashlib.sha256((old/'master.blend').read_bytes()).hexdigest()==old_manifest['master_sha256']==report['source_master_sha256']
    assert report['locked_geometry_before']==report['locked_geometry_after']
    assert set(report['locked_geometry_after'])==set(old_manifest['geometry_lock_objects'])
    assert len(report['locked_geometry_after'])==26 and report['locked_geometry_unchanged']
    assert report['print_approved'] is False

def test_palette_color_space_is_explicit_and_dark_colors_are_linearized():
    swatches=json.loads((DESIGN/'palette-swatches.json').read_text())
    assert swatches['color_space']=='sRGB'
    linear=srgb_to_linear_hex(swatches['clothing']['black'])
    assert 0<linear[0]<40/255 and linear[3]==1
    assert set(swatches['skin'])=={'light','warm','tan','deep'}

TETRA_VERTS=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
TETRA_FACES=[[0,2,1],[0,1,3],[1,2,3],[2,0,3]]

def test_closed_sample_and_broken_sample():
    assert inspect_topology(TETRA_VERTS,TETRA_FACES)['passed']
    broken=inspect_topology(TETRA_VERTS,TETRA_FACES[:-1])
    assert not broken['passed'] and broken['boundary_edges']==3

def test_nonfinite_and_nonmanifold_fail():
    assert not inspect_topology([[float('nan'),0,0]]+TETRA_VERTS[1:],TETRA_FACES)['passed']
    duplicate=inspect_topology(TETRA_VERTS,TETRA_FACES+[TETRA_FACES[0]])
    assert not duplicate['passed'] and duplicate['nonmanifold_edges']==3

def evidence(name):
    path=ROOT/'evidence/appearance-v2'/name
    if not (path/'provenance.json').exists():pytest.skip('Generate documented version-0.2 Blender evidence first')
    return path

def test_real_artifact_provenance_and_binary_formats():
    directory=evidence('neutral');p=json.loads((directory/'provenance.json').read_text())
    assert p['engine_version'].startswith('Blender 4.5') and p['design_version']==DESIGN_VERSION
    assert p['same_scene_export'] and p['head_morphs_baked']
    assert p['locked_geometry_before']==p['locked_geometry_after']
    assert p['status']=='DEMO_NOT_PRINT_APPROVED' and p['appearance_provider']=='manual-fixture'
    for item in p['artifacts']:
        content=(directory/item['filename']).read_bytes()
        assert hashlib.sha256(content).hexdigest()==item['sha256']
        assert item['model_revision']==p['model_revision'] and item['master_sha256']==p['master_sha256'] and item['params_sha256']==p['params_sha256']
    glb=(directory/'model.glb').read_bytes()
    assert glb[:4]==b'glTF' and struct.unpack('<I',glb[8:12])[0]==len(glb)
    stl=(directory/'model.stl').read_bytes()
    assert len(stl)==84+struct.unpack('<I',stl[80:84])[0]*50
    assert (directory/'preview.png').read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
    qa=json.loads((directory/'qa.json').read_text())
    assert qa['passed'] and qa['geometry']['head_morphs_baked'] and qa['geometry']['feature_envelopes_passed']
    assert qa['slicer']['state']=='NOT_RUN' and qa['print_approved'] is False
    checksum=p.pop('job_checksum')
    assert checksum==hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def test_contrasting_parameters_change_geometry_without_changing_locks():
    a=json.loads((evidence('neutral')/'provenance.json').read_text());b=json.loads((evidence('contrasting')/'provenance.json').read_text())
    assert a['params_sha256']!=b['params_sha256'] and a['configured_geometry_sha256']!=b['configured_geometry_sha256']
    assert a['master_sha256']==b['master_sha256'] and a['locked_geometry_before']==b['locked_geometry_after']
    assert json.loads((evidence('contrasting')/'qa.json').read_text())['passed']

def test_every_authored_morph_and_combined_extremes_pass_real_blender_stress():
    path=ROOT/'evidence/appearance-v2/morph-stress.json'
    if not path.exists():pytest.skip('Run documented Blender morph stress command first')
    report=json.loads(path.read_text());assert report['passed'] and report['cases']>=59
    cases={r['case']:r for r in report['results']}
    for key in FACE_MORPH_KEYS:
        for value in ('-1','+1'):
            case=cases[key+':'+value]
            assert case['passed'] and case['geometry_changed'] and case['locked_geometry_unchanged'] and case['head_morphs_baked']


def all_points_match(points,reference,tolerance=2e-5):
    # Spatial buckets avoid N-squared memory and tolerate only float32 export rounding.
    buckets={}
    for point in np.unique(reference,axis=0):buckets.setdefault(tuple(np.floor(point/tolerance).astype(int)),[]).append(point)
    offsets=list(itertools.product((-1,0,1),repeat=3))
    for point in np.unique(points,axis=0):
        cell=np.floor(point/tolerance).astype(int)
        found=False
        for offset in offsets:
            for candidate in buckets.get(tuple(cell+offset),()):
                if np.linalg.norm(point-candidate)<=tolerance:found=True;break
            if found:break
        if not found:return False
    return True

@pytest.mark.parametrize('name',['neutral','contrasting'])
def test_glb_and_stl_contain_same_baked_geometry(name):
    path=evidence(name);scene=trimesh.load(path/'model.glb',force='scene',process=False)
    chunks=[]
    for node in scene.graph.nodes_geometry:
        transform,geometry_name=scene.graph[node]
        vertices=np.asarray(scene.geometry[geometry_name].vertices)
        points=vertices@transform[:3,:3].T+transform[:3,3]
        chunks.append(points[:,[0,2,1]]*np.array([1,-1,1])) # glTF Y-up to source Z-up
    glb=np.concatenate(chunks)
    stl=trimesh.load(path/'model.stl',process=False).vertices
    assert all_points_match(glb,stl) and all_points_match(stl,glb)
    data=(path/'model.glb').read_bytes();length=struct.unpack_from('<I',data,12)[0];header=json.loads(data[20:20+length])
    assert all('targets' not in primitive for mesh in header['meshes'] for primitive in mesh['primitives'])


def fixture_provenance():
    return {'profile_id':'a'*32,'profile_revision':1,'profile_sha256':'b'*64,'source':'technical-fixture','analysis_version':'1.0','photo_sha256':[],'manual_overrides_sha256':'c'*64,'observations_sha256':'d'*64,'assignments_sha256':'e'*64,'consent_policy':'technical-fixture-v1','reviewed':True,'external_transfer':False}

def test_technical_fixture_metadata_accepts_no_photo_hashes():
    metadata=fixture_provenance()
    assert validate_appearance(metadata)==metadata
    metadata['photo_sha256']=['invalid']
    with pytest.raises(ValueError,match='photo hashes'):validate_appearance(metadata)

def test_browser_appearance_still_requires_real_photo_hashes():
    metadata=fixture_provenance();metadata.update(source='browser-mediapipe-v1',consent_policy='browser-local-v1')
    with pytest.raises(ValueError,match='photo hashes'):validate_appearance(metadata)
    metadata['photo_sha256']=['f'*64]
    assert validate_appearance(metadata)==metadata
