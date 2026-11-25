"""Run a checked-in Blender adapter. No fabricated artifacts when Blender is absent."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from packages.schemas.constants import DESIGN_ID, DESIGN_VERSION, PARAMS_SCHEMA_VERSION, FACE_MORPH_KEYS, HAIR_STYLES, HAIR_COLORS, SKIN_MATERIALS, CLOTHING_PALETTES, FACIAL_HAIR_STYLES, GLASSES_STYLES
from workers.blender.morphs import validate_morphs
DESIGN = ROOT / 'assets/designs' / DESIGN_ID / DESIGN_VERSION
ALLOWED = {
 'hair_style_asset_id': set(HAIR_STYLES), 'hair_color_id': set(HAIR_COLORS),
 'facial_hair_id': set(FACIAL_HAIR_STYLES), 'glasses_asset_id': set(GLASSES_STYLES),
 'skin_material_id': set(SKIN_MATERIALS), 'outfit_palette_id': set(CLOTHING_PALETTES),
 'pants_palette_id': set(CLOTHING_PALETTES), 'shoes_palette_id': set(CLOTHING_PALETTES),
}

def validate_params(data):
    if not isinstance(data,dict) or set(data) != {'schema_version','characters'} or data['schema_version'] != PARAMS_SCHEMA_VERSION:
        raise ValueError('Expected schema_version '+PARAMS_SCHEMA_VERSION+' and characters only')
    if not isinstance(data['characters'],dict) or set(data['characters']) != {'left','right'}:
        raise ValueError('Exactly left and right character slots are required')
    for slot, char in data['characters'].items():
        if not isinstance(char,dict) or set(char) != set(ALLOWED) | {'face_morphs','engraving_text'}:
            raise ValueError(f'{slot}: unknown or missing customization field')
        for key, options in ALLOWED.items():
            if not isinstance(char[key],str) or char[key] not in options:
                raise ValueError(f'{slot}: unsupported {key}')
        validate_morphs(char['face_morphs'])
        if not isinstance(char['engraving_text'],str) or not re.fullmatch(r'[A-Za-z -]{0,12}',char['engraving_text']):
            raise ValueError('Names support up to 12 ASCII letters, spaces, or hyphens')
    return data


def validate_appearance(data):
    expected={'profile_id','profile_revision','profile_sha256','source','analysis_version','photo_sha256','manual_overrides_sha256','observations_sha256','assignments_sha256','consent_policy','reviewed','external_transfer'}
    if not isinstance(data,dict) or set(data)!=expected:raise ValueError('Unexpected appearance provenance fields')
    if not isinstance(data['profile_id'],str) or not re.fullmatch(r'[a-f0-9]{32}',data['profile_id']):raise ValueError('Invalid appearance profile identifier')
    if type(data['profile_revision']) is not int or data['profile_revision']<1:raise ValueError('Invalid appearance profile revision')
    for key in ('profile_sha256','manual_overrides_sha256','observations_sha256','assignments_sha256'):
        if not isinstance(data[key],str) or not re.fullmatch(r'[a-f0-9]{64}',data[key]):raise ValueError('Invalid appearance hash')
    minimum_photos=0 if data.get('source')=='technical-fixture' else 1
    if not isinstance(data['photo_sha256'],list) or not minimum_photos<=len(data['photo_sha256'])<=3 or any(not isinstance(v,str) or not re.fullmatch(r'[a-f0-9]{64}',v) for v in data['photo_sha256']):raise ValueError('Invalid source photo hashes')
    if data['source'] not in ('browser-mediapipe-v1','technical-fixture') or data['analysis_version']!='1.0':raise ValueError('Unsupported appearance analysis source')
    if data['consent_policy'] not in ('browser-local-v1','technical-fixture-v1') or data['reviewed'] is not True or data['external_transfer'] is not False:raise ValueError('Appearance profile requires local processing and explicit review')
    return data

def find_blender():
    candidates = [os.getenv('BLENDER_BIN'), shutil.which('blender'),
      '/Applications/Blender.app/Contents/MacOS/Blender',
      str(ROOT.parent.parent / 'work/tools/blender/Blender.app/Contents/MacOS/Blender')]
    return next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()),None)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_manifest(manifest):
    required = {'design_id','version','status','master_blend_asset','master_sha256','character_slots','geometry_lock_objects','allowed_asset_slots','allowed_shape_keys','allowed_materials','engraving_constraints','attachment_anchors','assembly_part_ids','preview_cameras','export_units','print_profiles','validation_rules','print_approved'}
    if set(manifest) != required:
        raise ValueError('Manifest fields differ from strict demo schema')
    if manifest['design_id'] != DESIGN_ID or manifest['version'] != DESIGN_VERSION or manifest['print_approved'] is not False:
        raise ValueError('Only the unapproved demo design may run')
    master = (ROOT / manifest['master_blend_asset']).resolve()
    if not master.is_relative_to(DESIGN.resolve()) or not master.is_file() or sha(master) != manifest['master_sha256']:
        raise ValueError('Source master missing or SHA256 mismatch')
    if not manifest['geometry_lock_objects'] or set(manifest['character_slots']) != {'left','right'}:
        raise ValueError('Required locked geometry or character slots missing')
    if set(manifest['allowed_shape_keys'])!=set(FACE_MORPH_KEYS) or any(bounds!={'min':-1.0,'max':1.0,'default':0.0} for bounds in manifest['allowed_shape_keys'].values()):
        raise ValueError('Manifest must declare exactly the authored bounded morph controls')
    return master

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--params',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--revision',required=True,type=int)
    parser.add_argument('--blender')
    parser.add_argument('--appearance')
    parser.add_argument('--timeout',type=int,default=int(os.environ.get('BLENDER_TIMEOUT_SECONDS','540')))
    parser.add_argument('--threads',type=int,default=int(os.environ.get('BLENDER_THREADS','2')))
    args=parser.parse_args()
    if args.revision < 1: raise ValueError('Revision must be positive')
    if not 30 <= args.timeout <= 1100: raise ValueError('Blender timeout must be between 30 and 1100 seconds')
    if not 1 <= args.threads <= 8: raise ValueError('Blender threads must be between 1 and 8')
    params=validate_params(json.loads(Path(args.params).read_text()))
    master=verify_manifest(json.loads((DESIGN/'manifest.json').read_text()))
    blender=args.blender or find_blender()
    if not blender: raise RuntimeError('BLENDER_UNAVAILABLE: Install Blender 4.5 LTS and set BLENDER_BIN. No model artifacts were generated.')
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    clean=output/'validated-params.json'
    clean.write_text(json.dumps(params,sort_keys=True,indent=2))
    appearance_path=None
    if args.appearance:
        raw=Path(args.appearance).read_bytes()
        if len(raw)>32768:raise ValueError('Appearance provenance is too large')
        appearance=validate_appearance(json.loads(raw))
        appearance_path=output/'validated-appearance.json'
        appearance_path.write_text(json.dumps(appearance,sort_keys=True,indent=2))
    command=[blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--threads',str(args.threads),'--python',str(Path(__file__).with_name('scene.py')),'--','--master',str(master),'--params',str(clean),'--output',str(output),'--revision',str(args.revision)]
    if appearance_path:command.extend(['--appearance',str(appearance_path)])
    with (output/'blender.log').open('w') as log:
        try:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=args.timeout,check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('BLENDER_TIMEOUT: model build exceeded its time limit') from exc
    if result.returncode or not (output/'provenance.json').exists():
        raise RuntimeError('BLENDER_FAILED: inspect private blender.log for diagnostics')
    provenance=json.loads((output/'provenance.json').read_text())
    for item in provenance['artifacts']:
        if sha(output/item['filename']) != item['sha256']:
            raise RuntimeError('Artifact hash verification failed')
    qa=json.loads((output/'qa.json').read_text())
    if not qa.get('passed'):
        raise RuntimeError('GEOMETRY_QA_FAILED: inspect qa.json; generated artifacts require review')
    print(json.dumps({'state':'PREVIEW_READY','revision':args.revision,'provenance':str(output/'provenance.json')}))

if __name__ == '__main__':
    try: main()
    except (ValueError,RuntimeError,OSError,json.JSONDecodeError) as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)
