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
DESIGN=ROOT/'assets/designs/better-together/0.1.0-demo'
sys.path.insert(0,str(ROOT))
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

def base_half(side):
    # A visibly interlocking contour for the technical demo. Zero engineered clearance.
    sign=1 if side=='right' else -1
    points=[]
    for i in range(65):
        t=math.pi*i/64
        x=16*math.sin(t)**3*.14
        y=(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t)+4)*.14
        points.append((sign*x,y))
    if side=='right':
        join=[(0,-.55)]+[(.20*math.cos(-math.pi/2+math.pi*i/24),-.35+.20*math.sin(-math.pi/2+math.pi*i/24)) for i in range(1,25)]+[(0,points[0][1])]
    else:
        join=[(0,-.55)]+[(.20*math.cos(-math.pi/2+math.pi*i/24),-.35+.20*math.sin(-math.pi/2+math.pi*i/24)) for i in range(1,25)]+[(0,points[0][1])]
    points=points+join[:-1]
    n=len(points)
    verts=[(x+sign*.012,y,z) for z in (0,.32) for x,y in points]
    # Tessellate concave n-gons, retaining every boundary vertex.
    polygon=[Vector((x,y,0)) for x,y in points]
    triangles=tessellate_polygon([polygon])
    lookup={(round(v.x,8),round(v.y,8)):i for i,v in enumerate(polygon)}
    faces=[]
    for tri in triangles:
        ids=tuple(v if isinstance(v,int) else lookup[(round(v.x,8),round(v.y,8))] for v in tri)
        faces.append(tuple(reversed(ids)))
        faces.append(tuple(i+n for i in ids))
    for i in range(n):
        j=(i+1)%n;faces.append((i,j,j+n,i+n))
    mesh=bpy.data.meshes.new('HEART_BASE_'+side.upper());mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    finish(obj,mesh.name,material('base',PALETTE['base']),True,side,'base')
    bevel=obj.modifiers.new('Soft demo edges','BEVEL');bevel.width=.045;bevel.segments=3
    bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=bevel.name);obj.select_set(False)
    return obj

def build_character(slot,x):
    skin=material('SKIN_'+slot,PALETTE['warm'])
    outfit=material('OUTFIT_'+slot,PALETTE['cream' if slot=='left' else 'blue'])
    pants=material('PANTS_'+slot,PALETTE['pants'])
    shoes=material('SHOES',PALETTE['shoe'])
    # Seated proportions and hands are invariant under all customization parameters.
    body=sphere('BODY_'+slot.upper(),(x,.05,1.05),(.45,.38,.60),outfit,True,slot,'body')
    body.rotation_euler[1]=.06 if slot=='left' else -.06
    for j,d in enumerate((-.22,.22)):
        capsule(f'THIGH_{slot}_{j}',(x+d,.0,.63),(x+d,-.60,.61),.205,pants,True,slot,'legs')
        capsule(f'SHIN_{slot}_{j}',(x+d,-.56,.62),(x+d,-.86,.44),.16,pants,True,slot,'legs')
        sphere(f'SHOE_{slot}_{j}',(x+d,-1.02,.43),(.19,.30,.13),shoes,True,slot,'shoes')
    for j,d in enumerate((-.43,.43)):
        capsule(f'ARM_{slot}_{j}',(x+d,.02,1.37),(x+d*.85,-.36,.94),.14,outfit,True,slot,'arms')
        sphere(f'HAND_{slot}_{j}',(x+d*.85,-.43,.86),(.15,.13,.15),skin,True,slot,'hands')
    sphere('HEAD_'+slot.upper(),(x,-.015,1.99),(.51,.46,.55),skin,False,slot,'head')
    for j,d in enumerate((-.49,.49)):
        sphere(f'EAR_{slot}_{j}',(x+d,-.005,1.98),(.11,.085,.15),skin,False,slot,'head')
    sphere('NOSE_'+slot.upper(),(x,-.455,1.94),(.075,.095,.072),skin,False,slot,'face')
    eyes=material('EYES',PALETTE['eye'])
    for j,d in enumerate((-.18,.18)):
        sphere(f'EYE_{slot}_{j}',(x+d,-.435,2.045),(.031,.022,.042),eyes,False,slot,'face',24,16)
    smile=[(x+.12*math.cos(t),-.464,1.88+.047*math.sin(t)) for t in [math.pi+math.pi*i/16 for i in range(17)]]
    tube('SMILE_'+slot.upper(),smile,.012,eyes,slot)
    anchor=bpy.data.objects.new('ANCHOR_'+slot.upper(),None);bpy.context.collection.objects.link(anchor)
    anchor.location=(x,0,.32);anchor['locked']=True


def hair(slot,x,style,color):
    mat=material('HAIR_'+slot,PALETTE[color])
    # Sculpted clumps remain bounded to the authored demo envelope.
    sphere('HAIR_CAP_'+slot,(x,.06,2.36),(.50,.43,.24),mat,False,slot,'hair')
    for i in range(7):
        angle=math.pi*(.08+.84*i/6)
        sx=x+.43*math.cos(angle)
        sphere(f'FRINGE_{slot}_{i}',(sx,-.33,2.34+.09*math.sin(angle)),(.16,.18,.19),mat,False,slot,'hair',24,16)
    if style in ('long','bun'):
        for sign in (-1,1):
            sphere(f'LOCK_{slot}_{sign}',(x+sign*.43,.10,1.91),(.16,.28,.48),mat,False,slot,'hair')
    if style=='bun':
        sphere('BUN_'+slot,(x-.20,.16,2.64),(.24,.23,.25),mat,False,slot,'hair')
    if style=='long':
        sphere('BACK_HAIR_'+slot,(x,.28,1.87),(.44,.20,.58),mat,False,slot,'hair')

def configure(params):
    for slot,char in params['characters'].items():
        x=-.77 if slot=='left' else .77
        material('SKIN_'+slot,PALETTE[char['skin_material_id']])
        material('OUTFIT_'+slot,PALETTE[char['outfit_palette_id']])
        for obj in list(bpy.data.objects):
            if obj.get('character_slot')==slot and obj.get('category') in ('hair','beard','glasses','name'):
                bpy.data.objects.remove(obj,do_unlink=True)
        hair(slot,x,char['hair_style_asset_id'],char['hair_color_id'])
        if char['facial_hair_id']=='beard':
            mat=material('BEARD_'+slot,PALETTE[char['hair_color_id']])
            sphere('BEARD_'+slot,(x,-.25,1.74),(.37,.23,.20),mat,False,slot,'beard')
        if char['glasses_asset_id']=='round':
            for j,d in enumerate((-.18,.18)):
                coords=[(x+d+.125*math.cos(t),-.478,2.045+.115*math.sin(t)) for t in [math.tau*i/32 for i in range(33)]]
                obj=tube(f'GLASSES_{slot}_{j}',coords,.012,material('EYES',PALETTE['eye']),slot);obj['category']='glasses'
            obj=tube('BRIDGE_'+slot,[(x-.06,-.478,2.07),(x+.06,-.478,2.07)],.012,material('EYES',PALETTE['eye']),slot);obj['category']='glasses'
        if char['engraving_text']:
            curve=bpy.data.curves.new('NAME_'+slot,'FONT');curve.body=char['engraving_text'];curve.align_x='CENTER';curve.size=.145;curve.extrude=.006;curve.bevel_depth=.001
            obj=bpy.data.objects.new('NAME_'+slot,curve);bpy.context.collection.objects.link(obj)
            obj.location=(-.40 if slot=='left' else .40,-1.28,.33)
            bpy.context.view_layer.objects.active=obj;obj.select_set(True);bpy.ops.object.convert(target='MESH');obj=bpy.context.object;obj.select_set(False)
            weld(obj)
            finish(obj,'NAME_'+slot,material('NAME',PALETTE['name']),False,slot,'name')
            if obj.dimensions.x>.63:
                obj.scale*=.63/obj.dimensions.x
    bpy.context.view_layer.update()

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
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    for side in ('left','right'): base_half(side)
    build_character('left',-.77);build_character('right',.77)
    # Dedicated root empty objects make real assembled/separated viewing possible.
    for slot in ('left','right'):
        parent=bpy.data.objects.new('ASSEMBLY_'+slot.upper(),None);bpy.context.collection.objects.link(parent)
        for obj in list(bpy.data.objects):
            if obj.get('character_slot')==slot: obj.parent=parent
    bpy.context.scene.unit_settings.system='NONE'
    bpy.context.scene['design_id']='better-together';bpy.context.scene['version']='0.1.0-demo'
    DESIGN.mkdir(parents=True,exist_ok=True)
    path=DESIGN/'master.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    locked=sorted(obj.name for obj in bpy.data.objects if obj.get('locked'))
    manifest={
      'design_id':'better-together','version':'0.1.0-demo','status':'DEMO_NOT_PRINT_APPROVED',
      'master_blend_asset':str(path.relative_to(ROOT)),'master_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'character_slots':['left','right'],'geometry_lock_objects':locked,
      'allowed_asset_slots':{'hair_style_asset_id':['short','long','bun'],'facial_hair_id':['none','beard'],'glasses_asset_id':['none','round']},
      'allowed_shape_keys':{},'allowed_materials':{'hair_color_id':['chestnut','black','blonde','silver'],'skin_material_id':['warm','light','deep'],'outfit_palette_id':['cream','blue','rose','sage']},
      'engraving_constraints':{'max_characters':12,'pattern':'^[A-Za-z -]{0,12}$','max_width_scene_units':.63,'mode':'raised_demo_label','manufacturing_relief_validated':False},
      'attachment_anchors':{'left':'ANCHOR_LEFT','right':'ANCHOR_RIGHT'},'assembly_part_ids':['ASSEMBLY_LEFT','ASSEMBLY_RIGHT'],
      'preview_cameras':['three_quarter','front','side','back'],'export_units':'DEMO_SCENE_UNITS_NOT_MANUFACTURING_SCALE','print_profiles':[],
      'validation_rules':{'locked_geometry_tolerance':0,'require_finite_vertices':True,'require_closed_component_edges':True,'join_clearance_validated':False,'intersections_validated':False},
      'print_approved':False,
    }
    (DESIGN/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Created demo master',path)

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
    passed=all(c['finite'] and c['nonmanifold_edges']==0 and c['volume_scene_units']>0 for c in checks) and before==after
    return {'result':'DEMO_GEOMETRY_CHECKED' if passed else 'REVIEW_REQUIRED','passed':passed,'print_approved':False,'geometry':{'passed':passed,'locked_geometry_unchanged':before==after,'finite_vertices':all(c['finite'] for c in checks),'closed_components':all(c['nonmanifold_edges']==0 for c in checks),'component_count':len(checks),'dimensions_scene_units':dimensions,'units':'unscaled demo units','objects':checks},'slicer':{'state':'NOT_RUN','reason':'No validated print profile or target machine supplied'},'physical_validation':{'state':'NOT_APPROVED'},'limitations':['Overlapping mannequin components are not a fused production mesh.','Connector fit and wall thickness have not been engineered or physically tested.','Names are raised demonstration labels, not manufacturing-approved engraving.','STL contains geometry only; GLB materials do not transfer to STL.']}

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
    bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB',use_selection=True,export_yup=True,export_apply=True,export_extras=True,export_cameras=False,export_lights=False)
    export_stl(objects,out/'model.stl')
    progress(out,'MODEL_RENDERING');setup_render()
    bpy.context.scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
    progress(out,'QA_RUNNING')
    qa=qa_meshes(objects,before,after);(out/'qa.json').write_text(json.dumps(qa,indent=2))
    params_hash=hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    provenance={'design_id':manifest['design_id'],'design_version':manifest['version'],'model_revision':args.revision,'params_sha256':params_hash,'master_sha256':manifest['master_sha256'],'engine_version':'Blender '+bpy.app.version_string,'pipeline_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'status':'DEMO_NOT_PRINT_APPROVED','appearance_provider':'deterministic_mock','locked_geometry_before':before,'locked_geometry_after':after,'same_scene_export':True,'render_settings':{'resolution':bpy.context.scene.render.resolution_x,'samples':bpy.context.scene.cycles.samples,'denoise':bpy.context.scene.cycles.use_denoising,'threads':bpy.context.scene.render.threads},'export_units':manifest['export_units'],'artifacts':[]}
    for filename,kind in [('model.glb','glb'),('model.stl','stl'),('preview.png','png'),('qa.json','qa')]:
        path=out/filename
        provenance['artifacts'].append({'kind':kind,'filename':filename,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'model_revision':args.revision,'params_sha256':params_hash,'master_sha256':manifest['master_sha256']})
    provenance['job_checksum']=hashlib.sha256(json.dumps(provenance,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2))
    print('Build verified:',out)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--create-master',action='store_true');parser.add_argument('--master');parser.add_argument('--params');parser.add_argument('--output');parser.add_argument('--revision',type=int,default=1)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.create_master:create_master()
    else:build(args)
