"""Authored version-0.2 mannequin head, hair and feature recipes for Blender 4.5.

Only approved parameter values enter these functions. No photo, model text, path,
script, expression or network response is evaluated as executable geometry code.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector
from packages.schemas.constants import DESIGN_VERSION
from workers.blender.morphs import HEAD_KEYS, HEAD_RADII, HEAD_CENTER_Y, HEAD_CENTER_Z, deform_head_point, surface_point, srgb_to_linear_hex, neutral_morphs

ROOT=Path(__file__).resolve().parents[2]
SWATCHES=json.loads((ROOT/'assets/designs/better-together'/DESIGN_VERSION/'palette-swatches.json').read_text())


def material(name,color):
    mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes=True;mat.diffuse_color=color
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=color;shader.inputs['Roughness'].default_value=.66
    return mat


def palette_material(name,group,key):
    return material(name,srgb_to_linear_hex(SWATCHES[group][key]))


def finish(obj,name,mat,slot,category='face'):
    obj.name=name
    obj.data.materials.clear();obj.data.materials.append(mat)
    for p in obj.data.polygons:p.use_smooth=True
    obj['model_geometry']=True;obj['character_slot']=slot;obj['category']=category;obj['locked']=False
    obj.parent=bpy.data.objects['ASSEMBLY_'+slot.upper()]
    return obj


def sphere(name,position,scale,mat,slot,category='face',segments=24,rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,location=position)
    obj=bpy.context.object;obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(obj,name,mat,slot,category)


def capsule(name,a,b,radius,mat,slot,category='face'):
    direction=Vector(b)-Vector(a)
    obj=sphere(name,(Vector(a)+Vector(b))/2,(radius,radius,direction.length/2+radius),mat,slot,category)
    obj.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    return obj


def weld(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000005)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free();obj.data.update()


def tube(name,coords,radius,mat,slot,category='face'):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=16
    curve.bevel_depth=radius;curve.bevel_resolution=3;curve.use_fill_caps=True
    closed=(Vector(coords[0])-Vector(coords[-1])).length<.00001
    if closed:coords=coords[:-1]
    spline=curve.splines.new('POLY');spline.use_cyclic_u=closed;spline.points.add(len(coords)-1)
    for point,co in zip(spline.points,coords):point.co=(*co,1)
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action='DESELECT');bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.convert(target='MESH');obj=bpy.context.object;obj.select_set(False);weld(obj)
    return finish(obj,name,mat,slot,category)


def create_editable_master():
    """Replace only editable assets; preserve every locked source vertex/transform."""
    for obj in list(bpy.data.objects):
        if obj.get('model_geometry') and not obj.get('locked'):
            bpy.data.objects.remove(obj,do_unlink=True)
    for slot,x in [('left',-.77),('right',.77)]:
        skin=palette_material('SKIN_'+slot,'skin','warm')
        head=sphere('HEAD_'+slot.upper(),(x,HEAD_CENTER_Y,HEAD_CENTER_Z),HEAD_RADII,skin,slot,'head_morph',48,32)
        head.shape_key_add(name='Basis')
        basis=[tuple(v.co) for v in head.data.vertices]
        for name in HEAD_KEYS:
            key=head.shape_key_add(name=name);key.slider_min=-1;key.slider_max=1
            for point,co in zip(key.data,basis):point.co=deform_head_point(co,{name:1.0})
        head['authored_head_shape_keys']=json.dumps(list(HEAD_KEYS))


def face(slot,x,char):
    morphs=char['face_morphs'];skin=palette_material('SKIN_'+slot,'skin',char['skin_material_id'])
    hairmat=palette_material('HAIR_'+slot,'hair',char['hair_color_id'])
    dark=material('FACE_INK',srgb_to_linear_hex('#30251F'))
    whites=material('EYE_WHITE',srgb_to_linear_hex('#F3EADB'))
    lip_base=srgb_to_linear_hex(SWATCHES['skin'][char['skin_material_id']])
    lipmat=material('LIPS_'+slot,(lip_base[0]*.72,lip_base[1]*.46,lip_base[2]*.46,1))
    # Ears stay attached to the deformed side of the head rather than a fixed grid.
    for index,sign in enumerate((-1,1)):
        local=deform_head_point((sign*.495,0,-.025),morphs)
        sphere(f'EAR_{slot}_{index}',(x+local[0],HEAD_CENTER_Y,HEAD_CENTER_Z+local[2]),(.09,.075,.135),skin,slot)
    eye_x=.35+.065*morphs['eye_spacing'];eye_z=.12
    eye_scale=1+.27*morphs['eye_size']
    for index,sign in enumerate((-1,1)):
        pos=surface_point(x,sign*eye_x,eye_z,morphs,.003)
        sphere(f'EYE_WHITE_{slot}_{index}',pos,(.060*eye_scale,.014,.037*eye_scale),whites,slot)
        sphere(f'EYE_IRIS_{slot}_{index}',(pos[0],pos[1]-.014,pos[2]),(.031*eye_scale,.006,.028*eye_scale),dark,slot)
        sphere(f'EYE_GLINT_{slot}_{index}',(pos[0]-.006,pos[1]-.020,pos[2]+.009),(.006,.003,.007),whites,slot,segments=12,rings=8)
        brow=[]
        for j in range(13):
            t=j/12
            xn=sign*eye_x+(.20*(t-.5))
            zn=.31+(.055+.045*morphs['brow_arch'])*math.sin(math.pi*t)
            brow.append(surface_point(x,xn,zn,morphs,.016))
        tube(f'BROW_{slot}_{index}',brow,.016*(1+.5*morphs['brow_thickness']),hairmat,slot)
    nose_width=1+.35*morphs['nose_width'];projection=1+.30*morphs['nose_projection']
    top=surface_point(x,0,.10,morphs,.025*projection)
    bottom=surface_point(x,0,-.08,morphs,.065*projection)
    bridge=capsule('NOSE_BRIDGE_'+slot,top,bottom,.041,skin,slot)
    bridge.scale.x=nose_width
    tip=surface_point(x,0,-.095,morphs,.058*projection)
    sphere('NOSE_TIP_'+slot,tip,(.075*nose_width,.070*projection,.052),skin,slot)
    for index,sign in enumerate((-1,1)):
        sphere(f'NOSE_WING_{slot}_{index}',(tip[0]+sign*.055*nose_width,tip[1]+.013,tip[2]-.014),(.032*nose_width,.043,.025),skin,slot)
    half_width=.24*(1+.30*morphs['mouth_width'])
    # Neutral expression is a restrained smile; negative values flatten it gently.
    curve=.065+.055*morphs['smile']
    line=[];upper_lip=[]
    for j in range(25):
        t=-1+2*j/24;zn=-.265+curve*t*t
        line.append(surface_point(x,half_width*t,zn,morphs,.018))
        upper_lip.append(surface_point(x,half_width*t,zn+.012,morphs,.018))
    tube('LIP_'+slot,upper_lip,.014,lipmat,slot)
    tube('MOUTH_'+slot,line,.0065,dark,slot)


def buzz_scalp(slot,x,morphs,mat):
    """Closed thin shell follows the actual head, including its crown and hairline."""
    segments=40;rings=12;vertices=[]
    for offset in (.016,-.004):
        top=deform_head_point((0,0,HEAD_RADII[2]),morphs)
        vertices.append((x+top[0],HEAD_CENTER_Y+top[1],HEAD_CENTER_Z+top[2]+offset))
        for ring in range(1,rings+1):
            for index in range(segments):
                phi=math.tau*index/segments
                hairline=.135-.215*math.sin(phi)
                theta=math.acos(hairline)*ring/rings
                unit=(math.sin(theta)*math.cos(phi),math.sin(theta)*math.sin(phi),math.cos(theta))
                basis=tuple(unit[i]*HEAD_RADII[i] for i in range(3))
                deformed=deform_head_point(basis,morphs)
                normal=Vector(tuple(unit[i]/HEAD_RADII[i] for i in range(3))).normalized()
                vertices.append((x+deformed[0]+normal.x*offset,HEAD_CENTER_Y+deformed[1]+normal.y*offset,HEAD_CENTER_Z+deformed[2]+normal.z*offset))
    size=1+rings*segments;faces=[]
    for layer in range(2):
        start=layer*size
        for index in range(segments):
            triangle=(start,start+1+index,start+1+(index+1)%segments)
            faces.append(tuple(reversed(triangle)) if layer else triangle)
        for ring in range(rings-1):
            for index in range(segments):
                nxt=(index+1)%segments;a=start+1+ring*segments;b=a+segments
                quad=(a+index,b+index,b+nxt,a+nxt)
                faces.append(tuple(reversed(quad)) if layer else quad)
    last=1+(rings-1)*segments
    for index in range(segments):
        nxt=(index+1)%segments;faces.append((last+index,last+nxt,size+last+nxt,size+last+index))
    mesh=bpy.data.meshes.new('BUZZ_SCALP_'+slot);mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj);weld(obj)
    return finish(obj,obj.name,mat,slot,'hair')


def hair(slot,x,char):
    style=char['hair_style_asset_id']
    if style=='bald':return
    morphs=char['face_morphs'];mat=palette_material('HAIR_'+slot,'hair',char['hair_color_id'])
    width=1+.12*morphs['face_width']+.02*morphs['cheek_fullness']
    top=HEAD_CENTER_Z+deform_head_point((0,0,.55),morphs)[2]
    cap_z=top-.16
    if style=='buzz':
        buzz_scalp(slot,x,morphs,mat)
        return
    sphere('HAIR_CAP_'+slot,(x,.08,cap_z),(.505*width,.438,.205),mat,slot,'hair',32,20)
    if style in ('curly_short','curly_long'):
        for ring,radius in enumerate((.18,.35)):
            for i in range(7 if ring==0 else 9):
                angle=math.tau*i/(7 if ring==0 else 9)
                sphere(f'CURL_CROWN_{slot}_{ring}_{i}',(x+radius*width*math.cos(angle),.06+radius*.75*math.sin(angle),top+.025-.035*ring),(.12,.12,.115),mat,slot,'hair')
        for i in range(11):
            angle=math.pi*.06+math.pi*.88*i/10
            position=(x+.44*width*math.cos(angle),-.29,cap_z+.09*math.sin(angle))
            sphere(f'CURL_TOP_{slot}_{i}',position,(.13,.145,.13),mat,slot,'hair')
    else:
        for i in range(5):
            offset=(i-2)*.16*width
            clump=sphere(f'HAIR_SWEEP_{slot}_{i}',(x+offset,-.285,cap_z+.045+.055*(2-i)/4),(.14*width,.17,.115),mat,slot,'hair')
            clump.rotation_euler[1]=-.28
    if style in ('long','bun','bob','curly_long'):
        lower=1.57 if style in ('long','curly_long') else 1.72
        center=(top+lower)/2-.10
        height=(top-lower)/2
        sphere('HAIR_BACK_'+slot,(x,.28,center),(.47*width,.25,height),mat,slot,'hair',32,20)
        for sign in (-1,1):
            if style=='curly_long':
                for i in range(5):
                    z=lower+.09+(top-lower-.15)*i/4
                    sphere(f'CURL_SIDE_{slot}_{sign}_{i}',(x+sign*.475*width,.035,z),(.14,.19,.16),mat,slot,'hair')
            else:
                sphere(f'HAIR_SIDE_{slot}_{sign}',(x+sign*.445*width,.045,center),(.15,.25,height),mat,slot,'hair')
    if style=='bun':
        sphere('HAIR_BUN_'+slot,(x-.18*width,.18,top+.12),(.225,.22,.225),mat,slot,'hair')


def facial_hair(slot,x,char):
    style=char['facial_hair_id']
    if style=='none':return
    morphs=char['face_morphs'];mat=palette_material('HAIR_'+slot,'hair',char['hair_color_id'])
    if style in ('stubble','beard'):
        # A closed authored lower-face shell; no free-form reconstruction or identity mesh.
        density=5 if style=='stubble' else 7
        for row in range(3 if style=='stubble' else 4):
            zn=-.34-row*.105
            for col in range(density):
                xn=(col-(density-1)/2)*.135
                if row==0 and abs(xn)<.28:continue
                pos=surface_point(x,xn,zn,morphs,.012 if style=='stubble' else .035)
                sphere(f'BEARD_{slot}_{row}_{col}',pos,(.045 if style=='stubble' else .074,.019 if style=='stubble' else .047,.032 if style=='stubble' else .070),mat,slot,'beard',16,12)
    if style in ('moustache','beard'):
        for sign in (-1,1):
            points=[surface_point(x,sign*(.055+.19*j/8),-.17-.026*math.sin(math.pi*j/16),morphs,.027) for j in range(9)]
            tube(f'MOUSTACHE_{slot}_{sign}',points,.025,mat,slot,'beard')


def glasses(slot,x,char):
    style=char['glasses_asset_id']
    if style=='none':return
    morphs=char['face_morphs'];mat=material('GLASSES_FRAME',srgb_to_linear_hex('#463B32'))
    eye_x=.35+.065*morphs['eye_spacing']
    for index,sign in enumerate((-1,1)):
        coords=[]
        for j in range(49):
            angle=math.tau*j/48;c=math.cos(angle);s=math.sin(angle)
            if style=='rectangular':c=math.copysign(abs(c)**.55,c);s=math.copysign(abs(s)**.55,s)
            coords.append(surface_point(x,sign*eye_x+.225*c,.12+.165*s,morphs,.063))
        tube(f'GLASSES_{slot}_{index}',coords,.013,mat,slot,'glasses')
    tube('GLASSES_BRIDGE_'+slot,[surface_point(x,t,.15,morphs,.069) for t in [-.12,-.06,0,.06,.12]],.012,mat,slot,'glasses')
    for sign in (-1,1):
        start=surface_point(x,sign*(eye_x+.225),.14,morphs,.06)
        endpoint=(x+sign*.54*(1+.12*morphs['face_width']),-.02,HEAD_CENTER_Z+.08)
        capsule(f'GLASSES_ARM_{slot}_{sign}',start,endpoint,.012,mat,slot,'glasses')


def name_label(slot,char):
    if not char['engraving_text']:return
    curve=bpy.data.curves.new('NAME_'+slot,'FONT');curve.body=char['engraving_text'];curve.align_x='CENTER';curve.size=.145;curve.extrude=.006;curve.bevel_depth=.001
    obj=bpy.data.objects.new('NAME_'+slot,curve);bpy.context.collection.objects.link(obj)
    obj.location=(-.40 if slot=='left' else .40,-1.28,.33)
    bpy.ops.object.select_all(action='DESELECT');bpy.context.view_layer.objects.active=obj;obj.select_set(True)
    bpy.ops.object.convert(target='MESH');obj=bpy.context.object;obj.select_set(False);weld(obj)
    finish(obj,'NAME_'+slot,material('NAME',srgb_to_linear_hex('#F1D9B7')),slot,'name')
    if obj.dimensions.x>.63:obj.scale*=.63/obj.dimensions.x


def bake_heads():
    """Freeze one evaluated mesh for BOTH GLB and STL; raw shape-key bases cannot leak."""
    bpy.context.view_layer.update();depsgraph=bpy.context.evaluated_depsgraph_get()
    for slot in ('left','right'):
        obj=bpy.data.objects['HEAD_'+slot.upper()]
        if not obj.data.shape_keys:raise ValueError('Source head has no authored morph keys')
        evaluated=obj.evaluated_get(depsgraph)
        mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=depsgraph)
        obj.data=mesh;obj['head_morphs_baked']=True
    bpy.context.view_layer.update()


def configure(params,bake=True):
    for slot,char in params['characters'].items():
        x=-.77 if slot=='left' else .77
        head=bpy.data.objects.get('HEAD_'+slot.upper())
        if not head or not head.data.shape_keys:raise ValueError('Missing authored head morph asset')
        for name in HEAD_KEYS:
            key=head.data.shape_keys.key_blocks.get(name)
            if key is None:raise ValueError('Missing authored head shape key: '+name)
            key.value=char['face_morphs'][name]
        for obj in list(bpy.data.objects):
            if obj.get('character_slot')==slot and obj.get('model_geometry') and not obj.get('locked') and obj!=head:
                bpy.data.objects.remove(obj,do_unlink=True)
        palette_material('SKIN_'+slot,'skin',char['skin_material_id'])
        palette_material('OUTFIT_'+slot,'clothing',char['outfit_palette_id'])
        pants=palette_material('PANTS_'+slot,'clothing',char['pants_palette_id'])
        shoes=palette_material('SHOES_'+slot,'clothing',char['shoes_palette_id'])
        for obj in bpy.data.objects:
            if obj.get('character_slot')==slot and obj.get('category') in ('legs','shoes'):
                obj.data.materials.clear();obj.data.materials.append(shoes if obj.get('category')=='shoes' else pants)
        face(slot,x,char);hair(slot,x,char);facial_hair(slot,x,char);glasses(slot,x,char);name_label(slot,char)
    bpy.context.view_layer.update()
    if bake:bake_heads()
