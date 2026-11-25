"""Blender-only stress validation of the authored parameter envelope; no rendering."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import bpy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from packages.schemas.constants import FACE_MORPH_KEYS,HAIR_STYLES,FACIAL_HAIR_STYLES,GLASSES_STYLES,DESIGN_VERSION
from workers.blender.scene import locks,qa_meshes,fingerprint
from workers.blender.customize import configure


def digest(objects):
    return hashlib.sha256(json.dumps({obj.name:fingerprint(obj) for obj in objects if not obj.get('locked')},sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    design=ROOT/'assets/designs/better-together'/DESIGN_VERSION
    manifest=json.loads((design/'manifest.json').read_text());base=json.loads((design/'example-params.json').read_text())
    for slot in ('left','right'):base['characters'][slot]['engraving_text']=''
    cases=[('neutral',copy.deepcopy(base))]
    for key in FACE_MORPH_KEYS:
        for amount in (-1.0,1.0):
            params=copy.deepcopy(base);params['characters']['left']['face_morphs'][key]=amount
            cases.append((f'{key}:{amount:+.0f}',params))
    for style in HAIR_STYLES:
        params=copy.deepcopy(base);params['characters']['left']['hair_style_asset_id']=style
        cases.append(('hair:'+style,params))
    for beard in FACIAL_HAIR_STYLES:
        for glasses in GLASSES_STYLES:
            params=copy.deepcopy(base);params['characters']['right'].update(facial_hair_id=beard,glasses_asset_id=glasses)
            cases.append(('accessories:'+beard+':'+glasses,params))
    rng=random.Random(20261125)
    for index in range(12):
        params=copy.deepcopy(base)
        for slot in ('left','right'):
            char=params['characters'][slot]
            char['face_morphs']={key:rng.choice((-1.0,1.0)) if index<6 else rng.uniform(-1,1) for key in FACE_MORPH_KEYS}
            char.update(hair_style_asset_id=rng.choice(HAIR_STYLES),facial_hair_id=rng.choice(FACIAL_HAIR_STYLES),glasses_asset_id=rng.choice(GLASSES_STYLES))
        cases.append((f'combined:{index}',params))
    results=[];baseline=None;reference_locks=None
    for name,params in cases:
        bpy.ops.wm.open_mainfile(filepath=str(design/'master.blend'),load_ui=False)
        before=locks(manifest['geometry_lock_objects']);configure(params);after=locks(manifest['geometry_lock_objects'])
        if reference_locks is None:reference_locks=before
        objects=[o for o in bpy.data.objects if o.type=='MESH' and o.get('model_geometry')]
        qa=qa_meshes(objects,before,after);geometry_hash=digest(objects)
        if name=='neutral':baseline=geometry_hash
        changed=geometry_hash!=baseline
        morph_case=name.split(':')[0] in FACE_MORPH_KEYS
        result={'case':name,'passed':qa['passed'] and reference_locks==after and (changed if morph_case else True),'geometry_sha256':geometry_hash,'geometry_changed':changed,'locked_geometry_unchanged':before==after,'feature_envelopes_passed':qa['geometry']['feature_envelopes_passed'],'head_morphs_baked':qa['geometry']['head_morphs_baked']}
        if not result['passed']:
            result['bad_envelopes']=[item for item in qa['geometry']['feature_envelopes'] if not item['passed']]
            result['bad_topology']=[item for item in qa['geometry']['objects'] if item['nonmanifold_edges'] or item['volume_scene_units']<=0]
        results.append(result);print(json.dumps(result),flush=True)
    report={'design_version':DESIGN_VERSION,'master_sha256':manifest['master_sha256'],'engine_version':'Blender '+bpy.app.version_string,'cases':len(results),'passed':all(item['passed'] for item in results),'results':results,'print_approved':False}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
    if not report['passed']:raise RuntimeError('One or more authored morph stress cases failed')
    print('All',len(results),'authored morph/asset cases passed')

if __name__=='__main__':main()
