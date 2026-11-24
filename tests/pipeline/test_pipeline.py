import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from workers.blender.run import validate_params,verify_manifest,find_blender
from workers.qa.geometry import inspect_topology

@pytest.fixture
def params():
    return json.loads((ROOT/'assets/designs/better-together/0.1.0-demo/example-params.json').read_text())

def test_valid_params_and_rejected_unknown_fields(params):
    assert validate_params(params)==params
    params['characters']['left']['python']='print(1)'
    with pytest.raises(ValueError,match='unknown'):validate_params(params)

@pytest.mark.parametrize('field,value',[('hair_style_asset_id','freeform'),('skin_material_id','unsupported'),('face_morphs',{'smile':.2}),('engraving_text','../../private'),('engraving_text','A'*13)])
def test_unsupported_edits_rejected(params,field,value):
    params['characters']['right'][field]=value
    with pytest.raises(ValueError):validate_params(params)

def test_manifest_integrity_and_required_locks():
    manifest=json.loads((ROOT/'assets/designs/better-together/0.1.0-demo/manifest.json').read_text())
    assert verify_manifest(manifest).suffix=='.blend'
    tampered=copy.deepcopy(manifest);tampered['master_sha256']='0'*64
    with pytest.raises(ValueError,match='SHA256'):verify_manifest(tampered)
    missing=copy.deepcopy(manifest);missing['geometry_lock_objects']=[]
    with pytest.raises(ValueError,match='locked geometry'):verify_manifest(missing)

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

def test_real_artifact_provenance_and_binary_formats():
    directory=ROOT/'evidence/demo-build'
    if not (directory/'provenance.json').exists():pytest.skip('Run documented Blender fixture command first')
    provenance=json.loads((directory/'provenance.json').read_text())
    assert provenance['engine_version'].startswith('Blender 4.5')
    assert provenance['same_scene_export']
    assert provenance['locked_geometry_before']==provenance['locked_geometry_after']
    assert provenance['status']=='DEMO_NOT_PRINT_APPROVED'
    for item in provenance['artifacts']:
        content=(directory/item['filename']).read_bytes()
        assert hashlib.sha256(content).hexdigest()==item['sha256']
        assert item['model_revision']==provenance['model_revision']
        assert item['master_sha256']==provenance['master_sha256']
        assert item['params_sha256']==provenance['params_sha256']
    glb=(directory/'model.glb').read_bytes()
    assert glb[:4]==b'glTF' and struct.unpack('<I',glb[8:12])[0]==len(glb)
    stl=(directory/'model.stl').read_bytes()
    assert len(stl)==84+struct.unpack('<I',stl[80:84])[0]*50
    assert (directory/'preview.png').read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
    qa=json.loads((directory/'qa.json').read_text())
    assert qa['passed'] and qa['geometry']['locked_geometry_unchanged']
    assert qa['slicer']['state']=='NOT_RUN' and qa['print_approved'] is False
    checksum=provenance.pop('job_checksum')
    assert checksum==hashlib.sha256(json.dumps(provenance,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def test_alternate_customization_preserves_locked_master_geometry():
    demo=ROOT/'evidence/demo-build/provenance.json'
    variant=ROOT/'evidence/variant-build/provenance.json'
    if not demo.exists() or not variant.exists():pytest.skip('Generate both documented demo builds first')
    a=json.loads(demo.read_text());b=json.loads(variant.read_text())
    assert a['master_sha256']==b['master_sha256']
    assert a['params_sha256']!=b['params_sha256']
    assert a['locked_geometry_before']==b['locked_geometry_after']
    assert a['model_revision']==1 and b['model_revision']==2
    qa=json.loads((variant.parent/'qa.json').read_text())
    assert qa['passed'], [(x['object'],x['nonmanifold_edges']) for x in qa['geometry']['objects'] if x['nonmanifold_edges']]
