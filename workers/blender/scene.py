"""Known, version-controlled procedural placeholder and model export entry point.
Run --create-master once when authoring the demo, never from arbitrary request code.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import bpy
import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from packages.schemas.constants import DESIGN_ID, DESIGN_VERSION, FACE_MORPH_KEYS, HAIR_STYLES, HAIR_COLORS, SKIN_MATERIALS, CLOTHING_PALETTES, FACIAL_HAIR_STYLES, GLASSES_STYLES
DESIGN=ROOT/'assets/designs'/DESIGN_ID/DESIGN_VERSION
from workers.blender.customize import configure, create_editable_master
from workers.blender.morphs import HEAD_KEYS, FACE_ENVELOPE
from workers.qa.geometry import inspect_topology
PALETTE={
 'base':(0.61,0.27,0.20,1),'warm':(0.66,0.37,0.23,1),'light':(0.87,0.62,0.44,1),'deep':(0.29,0.13,0.08,1),
 'chestnut':(0.20,0.073,0.025,1),'black':(0.038,0.023,0.020,1),'blonde':(0.67,0.42,0.16,1),'silver':(0.47,0.43,0.39,1),
 'cream':(0.81,0.72,0.56,1),'blue':(0.15,0.25,0.32,1),'rose':(0.53,0.24,0.23,1),'sage':(0.30,0.38,0.27,1),
 'pants':(0.20,0.29,0.36,1),'shoe':(0.88,0.81,0.67,1),'eye':(0.04,0.025,0.018,1),'name':(0.99,0.86,0.68,1),
}

def material(name,color):
    mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes=True
    mat.diffuse_color=color
    bsdf=mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value=color
    bsdf.inputs['Roughness'].default_value=0.67
    return mat

def finish(obj,name,mat,locked=False,slot=None,category=None):
    obj.name=name
    if mat: obj.data.materials.append(mat)
    if obj.type=='MESH':
        for poly in obj.data.polygons: poly.use_smooth=True
    obj['locked']=locked
    if slot: obj['character_slot']=slot
    if category: obj['category']=category
    obj['model_geometry']=True
    return obj

def sphere(name,location,scale,mat,locked=False,slot=None,category=None,segments=32,rings=20):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=location)
    obj=bpy.context.object
    obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(obj,name,mat,locked,slot,category)

def capsule(name,start,end,radius,mat,locked=False,slot=None,category=None):
    mid=(Vector(start)+Vector(end))/2
    vec=Vector(end)-Vector(start)
    obj=sphere(name,mid,(radius,radius,vec.length/2+radius),mat,locked,slot,category)
    obj.rotation_euler=vec.to_track_quat('Z','Y').to_euler()
    return obj

def weld(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=0.000005)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free();obj.data.update()

def tube(name,coords,radius,mat,slot=None):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=16
    curve.bevel_depth=radius;curve.bevel_resolution=3;curve.resolution_u=16;curve.use_fill_caps=True
    closed=(Vector(coords[0])-Vector(coords[-1])).length<0.00001
    if closed: coords=coords[:-1]
    poly=curve.splines.new('POLY');poly.use_cyclic_u=closed;poly.points.add(len(coords)-1)
    for p,co in zip(poly.points,coords): p.co=(*co,1)
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.convert(target='MESH');obj=bpy.context.object
    obj.select_set(False)
    weld(obj)
    return finish(obj,name,mat,False,slot,'face')

def fingerprint(obj):
    data={'name':obj.name,'matrix':[[round(v,8) for v in row] for row in obj.matrix_world]}
    if obj.type=='MESH':
        data['vertices']=[[round(v,8) for v in vert.co] for vert in obj.data.vertices]
        data['faces']=[list(p.vertices) for p in obj.data.polygons]
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

def locks(names):
    missing=[name for name in names if name not in bpy.data.objects]
    if missing: raise ValueError('Missing required locked geometry: '+','.join(missing))
    return {name:fingerprint(bpy.data.objects[name]) for name in names}

def create_master():
    source=ROOT/'assets/designs/better-together/0.1.0-demo'
    old_manifest=json.loads((source/'manifest.json').read_text())
    old_master=source/'master.blend'
    source_hash=hashlib.sha256(old_master.read_bytes()).hexdigest()
    if source_hash!=old_manifest['master_sha256']:raise ValueError('Legacy source master hash mismatch')
    bpy.ops.wm.open_mainfile(filepath=str(old_master),load_ui=False)
    before=locks(old_manifest['geometry_lock_objects'])
    create_editable_master()
    defaults=json.loads((DESIGN/'example-params.json').read_text())
    configure(defaults,bake=False)
    after=locks(old_manifest['geometry_lock_objects'])
    if before!=after:raise ValueError('Master upgrade changed locked geometry')
    bpy.context.scene['design_id']=DESIGN_ID;bpy.context.scene['version']=DESIGN_VERSION
    path=DESIGN/'master.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path))
    manifest=dict(old_manifest)
    manifest.update(version=DESIGN_VERSION,master_blend_asset=str(path.relative_to(ROOT)),master_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest['allowed_asset_slots']={'hair_style_asset_id':list(HAIR_STYLES),'facial_hair_id':list(FACIAL_HAIR_STYLES),'glasses_asset_id':list(GLASSES_STYLES)}
    manifest['allowed_shape_keys']={key:{'min':-1.0,'max':1.0,'default':0.0} for key in FACE_MORPH_KEYS}
    manifest['allowed_materials']={'hair_color_id':list(HAIR_COLORS),'skin_material_id':list(SKIN_MATERIALS),'outfit_palette_id':list(CLOTHING_PALETTES),'pants_palette_id':list(CLOTHING_PALETTES),'shoes_palette_id':list(CLOTHING_PALETTES)}
    manifest['validation_rules'].update(require_feature_envelopes=True,require_unchanged_anchors=True)
    (DESIGN/'manifest.json').write_text(json.dumps(manifest,indent=2))
    report={'source_version':'0.1.0-demo','source_master_sha256':source_hash,'new_version':DESIGN_VERSION,'new_master_sha256':manifest['master_sha256'],'locked_geometry_unchanged':before==after,'locked_geometry_before':before,'locked_geometry_after':after,'stored_head_shape_keys':list(HEAD_KEYS),'surface_feature_controls':[k for k in FACE_MORPH_KEYS if k not in HEAD_KEYS],'feature_envelope_scene_units':FACE_ENVELOPE,'print_approved':False}
    (DESIGN/'master-upgrade-report.json').write_text(json.dumps(report,indent=2))
    print('Created versioned master with invariant locked geometry:',path)

def progress(output,state): (output/'progress.json').write_text(json.dumps({'state':state}))

def qa_meshes(objects,before,after):
    checks=[]
    for obj in objects:
        bm=bmesh.new();bm.from_mesh(obj.data)
        topology=inspect_topology([list(v.co) for v in obj.data.vertices],[list(f.vertices) for f in obj.data.polygons])
        boundary=topology['boundary_edges']
        nonmanifold=topology['nonmanifold_edges']
        finite=topology['finite']
        volume=abs(bm.calc_volume(signed=True));bm.free()
        checks.append({'object':obj.name,'vertices':len(obj.data.vertices),'faces':len(obj.data.polygons),'boundary_edges':boundary,'nonmanifold_edges':nonmanifold,'finite':finite,'volume_scene_units':round(volume,8)})
    verts=[obj.matrix_world@v.co for obj in objects for v in obj.data.vertices]
    dimensions=[round(max(v[i] for v in verts)-min(v[i] for v in verts),5) for i in range(3)]
    envelopes=[]
    for obj in objects:
        if obj.get('locked') or obj.get('category')=='name':continue
        slot=obj.get('character_slot');center=-.77 if slot=='left' else .77
        points=[obj.matrix_world@v.co for v in obj.data.vertices]
        low=[min(v[i] for v in points) for i in range(3)];high=[max(v[i] for v in points) for i in range(3)]
        good=(low[0]>=center-FACE_ENVELOPE['x_radius'] and high[0]<=center+FACE_ENVELOPE['x_radius'] and low[1]>=FACE_ENVELOPE['y_min'] and high[1]<=FACE_ENVELOPE['y_max'] and low[2]>=FACE_ENVELOPE['z_min'] and high[2]<=FACE_ENVELOPE['z_max'])
        envelopes.append({'object':obj.name,'passed':good,'min':[round(v,6) for v in low],'max':[round(v,6) for v in high]})
    envelope_pass=all(item['passed'] for item in envelopes)
    baked=all(bpy.data.objects['HEAD_'+slot].get('head_morphs_baked',False) and bpy.data.objects['HEAD_'+slot].data.shape_keys is None for slot in ('LEFT','RIGHT'))
    passed=all(c['finite'] and c['nonmanifold_edges']==0 and c['volume_scene_units']>0 for c in checks) and before==after and envelope_pass and baked
    return {'result':'DEMO_GEOMETRY_CHECKED' if passed else 'REVIEW_REQUIRED','passed':passed,'print_approved':False,'geometry':{'passed':passed,'locked_geometry_unchanged':before==after,'attachment_anchors_unchanged':all(before[name]==after[name] for name in ('ANCHOR_LEFT','ANCHOR_RIGHT')),'feature_envelopes_passed':envelope_pass,'feature_envelopes':envelopes,'head_morphs_baked':baked,'finite_vertices':all(c['finite'] for c in checks),'closed_components':all(c['nonmanifold_edges']==0 for c in checks),'component_count':len(checks),'dimensions_scene_units':dimensions,'units':'unscaled demo units','objects':checks},'slicer':{'state':'NOT_RUN','reason':'No validated print profile or target machine supplied'},'physical_validation':{'state':'NOT_APPROVED'},'limitations':['Overlapping mannequin components are not a fused production mesh.','Connector fit and wall thickness have not been engineered or physically tested.','Names are raised demonstration labels, not manufacturing-approved engraving.','STL contains geometry only; GLB materials do not transfer to STL.']}

def export_stl(objects,path):
    triangles=[]
    for obj in objects:
        mesh=obj.data;mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            vs=[obj.matrix_world@mesh.vertices[i].co for i in tri.vertices]
            normal=(vs[1]-vs[0]).cross(vs[2]-vs[0]).normalized()
            triangles.append(struct.pack('<12fH',*normal,*vs[0],*vs[1],*vs[2],0))
    with path.open('wb') as f:
        f.write(b'Keepsake3D DEMO candidate - NOT PRINT APPROVED'.ljust(80,b'\0'));f.write(struct.pack('<I',len(triangles)));f.writelines(triangles)

def setup_render():
    resolution=int(os.environ.get('BLENDER_RENDER_RESOLUTION','1000'))
    samples=int(os.environ.get('BLENDER_RENDER_SAMPLES','24'))
    denoise=os.environ.get('BLENDER_DENOISE','1')
    if not 256 <= resolution <= 1600: raise ValueError('Render resolution must be between 256 and 1600 pixels')
    if not 1 <= samples <= 64: raise ValueError('Render samples must be between 1 and 64')
    if denoise not in ('0','1'): raise ValueError('BLENDER_DENOISE must be 0 or 1')
    scene=bpy.context.scene
    scene.render.engine='CYCLES';scene.cycles.samples=samples;scene.cycles.use_denoising=denoise=='1'
    scene.render.resolution_x=resolution;scene.render.resolution_y=resolution;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
    scene.world.color=(.35,.30,.25)
    scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.75,.68,.59,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.55
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.055))
    floor=bpy.context.object;floor.name='RENDER_FLOOR';floor.data.materials.append(material('FLOOR',(.82,.76,.67,1)))
    bpy.ops.object.camera_add(location=(5.3,-8.5,6.1));camera=bpy.context.object;camera.name='PREVIEW_CAMERA';camera.rotation_euler=(Vector((0,-.12,1.1))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=5.9;scene.camera=camera
    for name,loc,power,size in [('KEY',(-3,-4,7),650,5),('FILL',(4,-1,4),350,4),('RIM',(1,4,6),500,3)]:
        bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.name=name;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()
    scene.view_settings.view_transform='AgX'

def build(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    progress(out,'MODEL_BUILDING')
    manifest=json.loads((DESIGN/'manifest.json').read_text());params=json.loads(Path(args.params).read_text())
    master=Path(args.master)
    appearance=json.loads(Path(args.appearance).read_text()) if args.appearance else {'source':'manual-fixture','reviewed':False,'external_transfer':False}
    if hashlib.sha256(master.read_bytes()).hexdigest()!=manifest['master_sha256']: raise ValueError('Master hash mismatch')
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
    before=locks(manifest['geometry_lock_objects'])
    configure(params)
    # Assign every newly configured ornament to its assembly parent without changing placement.
    for obj in bpy.data.objects:
        slot=obj.get('character_slot')
        if slot and obj.parent is None: obj.parent=bpy.data.objects.get('ASSEMBLY_'+slot.upper())
    bpy.context.view_layer.update()
    after=locks(manifest['geometry_lock_objects'])
    if before!=after: raise ValueError('Locked geometry changed')
    objects=[obj for obj in bpy.data.objects if obj.type=='MESH' and obj.get('model_geometry')]
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects: obj.select_set(True)
    for slot in ('LEFT','RIGHT'): bpy.data.objects['ASSEMBLY_'+slot].select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_morph=False,export_extras=True,export_cameras=False,export_lights=False)
    export_stl(objects,out/'model.stl')
    progress(out,'MODEL_RENDERING');setup_render()
    bpy.context.scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    progress(out,'QA_RUNNING')
    qa=qa_meshes(objects,before,after);(out/'qa.json').write_text(json.dumps(qa,indent=2))
    params_hash=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    provenance={'design_id':manifest['design_id'],'design_version':manifest['version'],'model_revision':args.revision,'params_sha256':params_hash,'master_sha256':manifest['master_sha256'],'engine_version':'Blender '+bpy.app.version_string,'pipeline_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'morph_recipe_sha256':hashlib.sha256(Path(__file__).with_name('customize.py').read_bytes()+Path(__file__).with_name('morphs.py').read_bytes()).hexdigest(),'palette_sha256':hashlib.sha256((DESIGN/'palette-swatches.json').read_bytes()).hexdigest(),'head_morphs_baked':True,'configured_geometry_sha256':hashlib.sha256(json.dumps({obj.name:fingerprint(obj) for obj in objects},sort_keys=True).encode()).hexdigest(),'status':'DEMO_NOT_PRINT_APPROVED','appearance_provider':appearance['source'],'appearance_profile':appearance,'locked_geometry_before':before,'locked_geometry_after':after,'same_scene_export':True,'render_settings':{'resolution':bpy.context.scene.render.resolution_x,'samples':bpy.context.scene.cycles.samples,'denoise':bpy.context.scene.cycles.use_denoising,'threads':bpy.context.scene.render.threads},'export_units':manifest['export_units'],'artifacts':[]}
    for filename,kind in [('model.glb','glb'),('model.stl','stl'),('preview.png','png'),('qa.json','qa')]:
        path=out/filename
        provenance['artifacts'].append({'kind':kind,'filename':filename,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'model_revision':args.revision,'params_sha256':params_hash,'master_sha256':manifest['master_sha256']})
    provenance['job_checksum']=hashlib.sha256(json.dumps(provenance,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
    print('Build verified:',out)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--create-master',action='store_true');parser.add_argument('--master');parser.add_argument('--params');parser.add_argument('--output');parser.add_argument('--revision',type=int,default=1);parser.add_argument('--appearance')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.create_master:create_master()
    else:build(args)
