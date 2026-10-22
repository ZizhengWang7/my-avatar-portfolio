"""Non-destructive head-rig refinement and diagnostic pose comparisons.

Never changes the source GLBs, previous .blend, or website. One avatar mesh is
loaded at a time. Diagnostic vertex colors are removed before saving/exporting.
"""
from array import array
import hashlib
import json
import math
from pathlib import Path
import resource
import sys

import bpy
import numpy as np
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rig_avatar_head import appearance_signature, geometry_digest, read_glb
from inspect_avatar import Components

SOURCE = ROOT / 'reports/my-avatar-head-prototype.blend'
WORKING = ROOT / 'reports/my-avatar-head-refined.blend'
OUTPUT = ROOT / 'public/models/my-avatar-head-refined.glb'
OUT = ROOT / 'reports/avatar-head-refinement'
PROTECTED = [SOURCE, ROOT / 'public/assets/人物3d建模.glb', ROOT / 'public/models/my-avatar-head-test.glb']
PROTECTED += [p for p in (ROOT/'src').rglob('*') if p.is_file()]
PROTECTED += [p for p in (ROOT/'backups').rglob('*') if p.is_file()]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value*value*(3-2*value)


def setup():
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    obj = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
    for bone in rig.pose.bones:
        bone.rotation_mode = 'QUATERNION'
        bone.rotation_quaternion.identity()
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 520
    scene.render.resolution_y = 620
    scene.render.resolution_percentage = 100
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = False
    scene.view_settings.view_transform = 'Standard'
    scene.render.image_settings.file_format = 'PNG'
    return scene, obj, rig


def render(scene, name, view='side', close=False):
    camera = scene.camera
    target = Vector((0, 0, -0.15)) if close else Vector((0, 0, 0))
    offset = {'front': (0, -4, 0), 'quarter': (2.8, -3, 0), 'side': (4, 0, 0)}[view]
    camera.location = target + Vector(offset)
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = 0.95 if close else 2.35
    path = OUT / f'{name}-{view}{"-close" if close else ""}.png'
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path.relative_to(ROOT))


def pose(rig, yaw=0, pitch=0, roll=0, coupled=False):
    world_rotation = Quaternion((0, 0, 1), math.radians(yaw)) @ Quaternion((1, 0, 0), math.radians(pitch)) @ Quaternion((0, -1, 0), math.radians(roll))
    for name in ('torso', 'neck', 'head'):
        rig.pose.bones[name].rotation_quaternion.identity()
    for name, fraction in ([('neck', 0.3), ('head', 0.7)] if coupled else [('head', 1)]):
        bone = rig.pose.bones[name]
        basis = (rig.matrix_world @ bone.bone.matrix_local).to_quaternion()
        rotation = world_rotation if fraction == 1 else world_rotation.slerp(Quaternion(), 1-fraction)
        bone.rotation_quaternion = basis.inverted() @ rotation @ basis
    bpy.context.view_layer.update()


def diagnose(scene, obj, rig):
    world = obj.matrix_world
    head_group = obj.vertex_groups['head'].index
    records = []
    for vertex in obj.data.vertices:
        p = world @ vertex.co
        weight = next((g.weight for g in vertex.groups if g.group == head_group), 0)
        if -0.33 < p.z < -0.06:
            records.append([p.x, p.y, p.z, weight])
    values = np.array(records)
    region_stats = []
    for low, high in [(-0.32,-0.24),(-0.24,-0.20),(-0.20,-0.16),(-0.16,-0.12),(-0.12,-0.08)]:
        for front, back in [(-0.6,-0.3),(-0.3,-0.18),(-0.18,0), (0,0.18),(0.18,0.4)]:
            mask = (values[:,2]>=low)&(values[:,2]<high)&(values[:,1]>=front)&(values[:,1]<back)
            subset = values[mask]
            if len(subset):
                region_stats.append({'z':[low,high], 'y':[front,back], 'vertices':len(subset),
                                     'head_weight_min':float(subset[:,3].min()), 'head_weight_max':float(subset[:,3].max())})
    report = {'bones': [{'name':b.name,'head_world':list(rig.matrix_world@b.head_local), 'tail_world':list(rig.matrix_world@b.tail_local)} for b in rig.data.bones], 'transition_regions':region_stats}
    for yaw in [0,35]:
        pose(rig,yaw)
        for view in ['front','quarter','side']:
            render(scene, f'baseline-yaw-{yaw}',view)
            if view=='side': render(scene, f'baseline-yaw-{yaw}',view,True)
    pose(rig)
    colors = obj.data.color_attributes.new(name='TemporaryHeadWeight', type='FLOAT_COLOR', domain='POINT')
    data = np.zeros((len(obj.data.vertices),4),dtype=np.float32)
    for vertex in obj.data.vertices:
        weight = next((g.weight for g in vertex.groups if g.group==head_group),0)
        data[vertex.index] = (weight,0.15,1-weight,1)
    colors.data.foreach_set('color',data.ravel())
    obj.data.color_attributes.active_color = colors
    scene.display.shading.color_type='VERTEX'
    for view in ['front','quarter','side']:render(scene,'baseline-head-weight',view,True)
    scene.display.shading.color_type='TEXTURE'
    obj.data.color_attributes.remove(colors)
    return report


def texture_samples(obj):
    material=obj.data.materials[0]
    shader=next(n for n in material.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    texture=shader.inputs['Base Color'].links[0].from_node
    image=texture.image
    pixels=np.empty(len(image.pixels),dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels=pixels.reshape((image.size[1],image.size[0],4))
    colours=np.zeros((len(obj.data.vertices),3),dtype=np.float32)
    # Export seams have their own vertices, so a loop UV per vertex suffices.
    uv=obj.data.uv_layers.active
    for loop in obj.data.loops:
        u,v=uv.data[loop.index].uv
        x=min(image.size[0]-1,max(0,int(u*image.size[0])))
        y=min(image.size[1]-1,max(0,int(v*image.size[1])))
        colours[loop.vertex_index]=pixels[y,x,:3]
    return colours


def refine(obj,rig):
    before=geometry_digest(obj.data)
    colours=texture_samples(obj)
    world=obj.matrix_world.copy()
    # Texture alone cannot distinguish a dark sticker, hair, and jacket.
    # Trace connected dark surfaces (including virtual UV-seam adjacency),
    # then classify them by high hair / low garment seed regions.
    dark=(colours[:,0]-colours[:,2]<0.085)|(colours[:,0]<0.12)
    connectivity=Components(len(obj.data.vertices))
    for edge in obj.data.edges:
        a,b=edge.vertices
        if dark[a] and dark[b]:connectivity.join(a,b)
    coincident={}
    for vertex in obj.data.vertices:
        if dark[vertex.index]:
            key=tuple(round(c/2e-7) for c in vertex.co)
            if key in coincident:connectivity.join(vertex.index,coincident[key])
            else:coincident[key]=vertex.index
    del coincident
    parts={}
    for vertex in obj.data.vertices:
        if dark[vertex.index]:
            root=connectivity.find(vertex.index)
            p=world@vertex.co
            part=parts.setdefault(root,{'min_z':1e6,'max_z':-1e6,'vertices':0})
            part['min_z']=min(part['min_z'],p.z)
            part['max_z']=max(part['max_z'],p.z)
            part['vertices']+=1
    ambiguous=[p for p in parts.values() if p['min_z'] < -0.45 and p['max_z'] > 0.15]
    if ambiguous:raise RuntimeError('Dark surface connects hair and garment; semantic review needed.')
    # Collar is near-neutral black/gray; exposed skin is warm. Restrict this
    # classifier to the lower neck/collar band, never the face or hair.
    clothing=[]
    weights=[]
    for vertex in obj.data.vertices:
        p=world@vertex.co
        part=parts[connectivity.find(vertex.index)] if dark[vertex.index] else None
        is_hair=part is not None and part['max_z']>0.15
        is_garment=part is not None and part['min_z'] < -0.45
        collar=p.z < -0.16 and is_garment
        if p.z < -0.45: collar=True
        # Oblique jaw attachment: the chin is lower than the back of the jaw.
        attachment=-0.25+0.45*(p.y+0.18)
        t=smooth((p.z-(attachment-0.22))/0.22)
        if collar: t=0
        # Stickers can be dark/gray just like clothing. Geometry must override
        # the texture classifier on the entire forward chin and rear hair tips.
        jaw=smooth((-p.y-0.12)/0.06)*smooth((p.z+0.37)/0.03)
        t=max(t,jaw)
        if is_hair:t=1
        # Hair's warm highlights are not in the dark mask. The diagnostic
        # garment component ends at z=-0.24109, leaving a small verified gap
        # below this rear-head protection boundary.
        if p.y > 0.16 and p.z > -0.23:t=1
        if is_garment and p.z < -0.16:t=0
        weights.append(t)
        if collar:clothing.append(vertex.index)
    del colours
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    bones=rig.data.edit_bones
    bones['neck'].use_connect=False
    bones['head'].use_connect=False
    bones['torso'].tail=(0,0.08,-0.40)
    bones['neck'].head=(0,0.08,-0.40)
    bones['neck'].tail=(0,0.06,-0.15)
    bones['head'].head=(0,0.06,-0.15)
    bones['head'].tail=(0,0.06,0.65)
    bones['neck'].use_connect=True
    bones['head'].use_connect=True
    bpy.ops.object.mode_set(mode='OBJECT')
    for group in list(obj.vertex_groups):obj.vertex_groups.remove(group)
    groups={name:obj.vertex_groups.new(name=name) for name in ['torso','neck','head']}
    rigid_head=[];rigid_torso=[];blended=0
    for index,t in enumerate(weights):
        if t==0:rigid_torso.append(index)
        elif t==1:rigid_head.append(index)
        else:
            for name,weight in zip(['torso','neck','head'],[(1-t)**2,2*t*(1-t),t*t]):
                groups[name].add([index],weight,'REPLACE')
            blended+=1
    groups['head'].add(rigid_head,1,'REPLACE')
    groups['torso'].add(rigid_torso,1,'REPLACE')
    assert geometry_digest(obj.data)==before
    return {'head_pivot_world':[0,0.06,-0.15], 'neck_base_world':[0,0.08,-0.40],
            'weight_rule':'Oblique jaw boundary z=-0.25+0.45*(y+0.18), blend extends 0.22 units below; smooth rigid-chin protection; connected dark hair/garment classes plus rear hair highlight protection above z=-0.23. No geometry or UV changes.',
            'rigid_head_vertices':len(rigid_head),'fixed_torso_vertices':len(rigid_torso),'blend_vertices':blended,
            'dark_components':len(parts), 'largest_dark_components':sorted(parts.values(),key=lambda p:p['vertices'],reverse=True)[:12],
            'fixed_indices':rigid_torso}


def finalize(scene,obj,rig):
    if WORKING.exists() or OUTPUT.exists():
        raise RuntimeError('Refined output already exists; choose new output names instead of overwriting.')
    original_geometry=geometry_digest(obj.data)
    refinement=refine(obj,rig)
    fixed=refinement.pop('fixed_indices')
    original=[obj.matrix_world@obj.data.vertices[i].co for i in fixed]
    poses=[('neutral',0,0,0)]
    for yaw in [15,20,25,30,35]:
        for sign in [-1,1]:poses.append((f'yaw{sign*yaw:+d}',sign*yaw,0,0))
    for pitch in [10,15,20]:
        for sign in [-1,1]:poses.append((f'pitch{sign*pitch:+d}',0,sign*pitch,0))
    for yaw in [-30,30]:
        for pitch in [-10,10]:poses.append((f'combined{yaw:+d}{pitch:+d}',yaw,pitch,3 if yaw>0 else -3))
    for yaw in [-35,35]:
        for pitch in [-15,15,-20,20]:poses.append((f'extreme{yaw:+d}{pitch:+d}',yaw,pitch,5 if yaw>0 else -5))
    results=[]
    for name,yaw,pitch,roll in poses:
        pose(rig,yaw,pitch,roll)
        evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        error=max(((evaluated.matrix_world@evaluated.data.vertices[i].co)-p).length for i,p in zip(fixed,original))
        assert error<1e-5, 'Fixed torso moved'
        files=[render(scene,'refined-'+name,view) for view in ['front','quarter','side']]
        if abs(yaw)>=30 or abs(pitch)>=15 or name=='neutral':
            files.append(render(scene,'refined-'+name,'side',True))
        results.append({'name':name,'yaw':yaw,'pitch':pitch,'roll':roll,'fixed_vertices':len(fixed),'max_fixed_displacement':error,'previews':files})
    pose(rig)
    assert geometry_digest(obj.data)==original_geometry, 'Geometry or UVs changed'
    render(scene,'refined-neutral-final','front')
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(WORKING))
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True);rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT),export_format='GLB',use_selection=True,
                              export_skins=True,export_animations=False,export_apply=False)
    gltf=read_glb(OUTPUT)
    skin=gltf['skins'][0]
    joints=[gltf['nodes'][i]['name'] for i in skin['joints']]
    assert {'torso','neck','head'}.issubset(joints)
    assert all('JOINTS_0' in p['attributes'] and 'WEIGHTS_0' in p['attributes'] for mesh in gltf['meshes'] for p in mesh['primitives'])
    assert appearance_signature(OUTPUT)==appearance_signature(PROTECTED[1]),'Material/texture changed'
    refinement.update({'poses':results,'working_copy':str(WORKING.relative_to(ROOT)),'glb':str(OUTPUT.relative_to(ROOT)),
                       'export_validation':{'joint_names':joints,'skinning_present':True,'material_semantics_and_texture_payloads_identical':True,'geometry_uv_hash_unchanged':True,'bytes':OUTPUT.stat().st_size},
                       'corrective_shape_keys':'Not added; first address weights and pivots. Blender drivers would require explicit runtime morph control after glTF export.',
                       'visual_review':'Pending final rendered sweep review; numeric checks do not establish visual safety.'})
    return refinement


def contacts():
    path=OUT/'refinement-report.json'
    report=json.loads(path.read_text())
    groups=[report['poses'][i:i+4] for i in range(0,len(report['poses']),4)]
    groups.insert(0,[{'name':'original yaw +35','previews':[str((OUT/f'baseline-yaw-35-{v}.png').relative_to(ROOT)) for v in ['front','quarter','side']]},
                     {'name':'refined yaw +35','previews':[str((OUT/f'refined-yaw+35-{v}.png').relative_to(ROOT)) for v in ['front','quarter','side']]}])
    sheets=[]
    for i,group in enumerate(groups):
        width,height=390,465
        pixels=np.zeros((len(group)*height,width*3,4),dtype=np.float32)
        for row,p in enumerate(group):
            for col,filename in enumerate(p['previews'][:3]):
                image=bpy.data.images.load(str(ROOT/filename),check_existing=False)
                image.scale(width,height)
                data=np.empty(width*height*4,dtype=np.float32)
                image.pixels.foreach_get(data)
                r=len(group)-1-row
                pixels[r*height:(r+1)*height,col*width:(col+1)*width]=data.reshape(height,width,4)
                bpy.data.images.remove(image)
        sheet=bpy.data.images.new(f'Refinement-{i}',width=width*3,height=len(group)*height,alpha=True)
        sheet.pixels.foreach_set(pixels.ravel())
        sheet.filepath_raw=str(OUT/f'comparison-sheet-{i}.png')
        sheet.file_format='PNG';sheet.save()
        sheets.append({'path':str(Path(sheet.filepath_raw).relative_to(ROOT)),'rows_top_to_bottom':[p['name'] for p in group], 'columns':['front','quarter','side']})
        bpy.data.images.remove(sheet)
    report['contact_sheets']=sheets
    path.write_text(json.dumps(report,indent=2)+'\n')


def validate_export():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(OUTPUT))
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
    scene=bpy.context.scene
    scene.render.engine='BLENDER_WORKBENCH'
    scene.render.resolution_x=520;scene.render.resolution_y=620
    scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.display.shading.color_type='TEXTURE'
    scene.display.shading.light='STUDIO'
    scene.display.shading.show_shadows=True
    scene.display.shading.background_type='WORLD'
    scene.world=bpy.data.worlds.new('RoundtripWorld');scene.world.color=(0.72,0.67,0.8)
    scene.view_settings.view_transform='Standard'
    bpy.ops.object.camera_add();scene.camera=bpy.context.object
    scene.camera.data.type='ORTHO'
    for bone in rig.pose.bones:bone.rotation_mode='QUATERNION'
    files=[]
    for name,yaw,pitch,roll in [('neutral',0,0,0),('yaw35',35,0,0),('yaw-35',-35,0,0),('combined',30,-10,3)]:
        pose(rig,yaw,pitch,roll)
        files += [render(scene,'roundtrip-'+name,view) for view in ['front','quarter','side']]
        if yaw:files.append(render(scene,'roundtrip-'+name,'side',True))
    report_path=OUT/'refinement-report.json'
    report=json.loads(report_path.read_text())
    report['export_validation']['roundtrip_import_successful']=True
    report['export_validation']['roundtrip_previews']=files
    report['roundtrip_process_peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,1)
    report_path.write_text(json.dumps(report,indent=2)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    if '--contacts' in sys.argv:
        contacts()
        return
    if '--validate-export' in sys.argv:
        validate_export()
        return
    hashes={str(p.relative_to(ROOT)):digest(p) for p in PROTECTED}
    scene,obj,rig=setup()
    if '--finalize' in sys.argv:
        report=finalize(scene,obj,rig)
    elif '--candidate' in sys.argv:
        report=refine(obj,rig)
        fixed=report.pop('fixed_indices')
        for name,yaw,pitch in [('neutral',0,0),('yaw35',35,0),('yaw-35',-35,0),('up20',0,-20),('down20',0,20),('combined',30,-15)]:
            pose(rig,yaw,pitch)
            for view in ['front','quarter','side']:
                render(scene,'candidate-v4-'+name,view)
                if view=='side':render(scene,'candidate-v4-'+name,view,True)
        pose(rig)
        colours=obj.data.color_attributes.new(name='TemporaryRefinedWeight',type='FLOAT_COLOR',domain='POINT')
        values=np.zeros((len(obj.data.vertices),4),dtype=np.float32)
        for vertex in obj.data.vertices:
            h=next((g.weight for g in vertex.groups if obj.vertex_groups[g.group].name=='head'),0)
            values[vertex.index]=(h,0.15,1-h,1)
        colours.data.foreach_set('color',values.ravel())
        obj.data.color_attributes.active_color=colours
        scene.display.shading.color_type='VERTEX'
        for view in ['front','quarter','side']:render(scene,'candidate-v4-head-weight',view,True)
        obj.data.color_attributes.remove(colours)
        scene.display.shading.color_type='TEXTURE'
    else:
        report=diagnose(scene,obj,rig)
    report['protected_hashes']=hashes
    report['protected_files_unchanged']=all(digest(ROOT/p)==h for p,h in hashes.items())
    report['process_peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,1)
    reportname='refinement-report.json' if '--finalize' in sys.argv else 'candidate.json' if '--candidate' in sys.argv else 'diagnosis.json'
    (OUT/reportname).write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
