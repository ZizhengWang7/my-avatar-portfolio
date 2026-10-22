"""Separate masked eye-texture prototype. Never writes existing source assets.

--bake samples the existing eye surface into local projection textures.
The default mode builds a new Blender working copy and diagnostic gaze renders.
"""
import hashlib
import json
import math
from pathlib import Path
import resource
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import barycentric_transform

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rig_avatar_head import appearance_signature
import refine_avatar_head as preview

SOURCE=ROOT/'public/models/my-avatar-head-refined.glb'
OUT=ROOT/'reports/avatar-eye-prototype'
ASSETS=ROOT/'public/models/avatar-eye-prototype'
WORKING=OUT/'avatar-eye-tracking-prototype.blend'
NEUTRAL=ROOT/'public/models/my-avatar-eye-prototype-neutral.glb'
SIZE=384
RANGE_X=0.003
RANGE_Y=0.002
EYES=[('viewer-left',-0.145),('viewer-right',0.145)]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()


def protect():
    OUT.mkdir(parents=True,exist_ok=True)
    ASSETS.mkdir(parents=True,exist_ok=True)
    path=OUT/'protected-inputs.json'
    if not path.exists():
        paths=[p for folder in ['src','backups','public'] for p in (ROOT/folder).rglob('*') if p.is_file() and ASSETS not in p.parents]
        paths += [p for p in (ROOT/'reports').rglob('*.blend') if OUT not in p.parents]
        hashes={str(p.relative_to(ROOT)):digest(p) for p in paths}
        path.write_text(json.dumps(hashes,indent=2)+'\n')
    hashes=json.loads(path.read_text())
    assert all(digest(ROOT/name)==value for name,value in hashes.items()),'Protected input changed'
    return hashes


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    return obj,rig


def upstream_image(socket):
    node=socket.links[0].from_node
    if node.type=='TEX_IMAGE':return node.image
    for entry in node.inputs:
        if entry.is_linked:
            try:return upstream_image(entry)
            except (IndexError,ValueError):pass
    raise ValueError('Image not found')


def pixels(image):
    data=np.empty(len(image.pixels),dtype=np.float32)
    image.pixels.foreach_get(data)
    return data.reshape(image.size[1],image.size[0],4)


def image_file(name,data,color_space='sRGB'):
    image=bpy.data.images.new(name,width=data.shape[1],height=data.shape[0],alpha=True)
    image.colorspace_settings.name=color_space
    image.pixels.foreach_set(np.ascontiguousarray(data,dtype=np.float32).ravel())
    image.filepath_raw=str(ASSETS/f'{name}.png');image.file_format='PNG';image.save()
    image.pack()
    return image


def sample(source,uv):
    # Match bilinear normalized image lookup, wrapping as in the original GLB.
    height,width=source.shape[:2]
    x=uv[:,:,0]*width-0.5;y=uv[:,:,1]*height-0.5
    x0=np.floor(x).astype(np.int32);y0=np.floor(y).astype(np.int32)
    fx=(x-x0)[:,:,None];fy=(y-y0)[:,:,None]
    return ((source[y0%height,x0%width]*(1-fx)+source[y0%height,(x0+1)%width]*fx)*(1-fy)+
            (source[(y0+1)%height,x0%width]*(1-fx)+source[(y0+1)%height,(x0+1)%width]*fx)*fy).astype(np.float32)


def bake(obj):
    mesh=obj.data;world=obj.matrix_world;inverse=world.inverted()
    direction=(inverse.to_3x3()@Vector((0,1,0))).normalized()
    shader=next(n for n in mesh.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    source_base=pixels(upstream_image(shader.inputs['Base Color']))
    source_mr=pixels(upstream_image(shader.inputs['Roughness']))
    cache={};uv_layer=mesh.uv_layers.active
    config={'source':str(SOURCE.relative_to(ROOT)),'range_x':RANGE_X,'range_y':RANGE_Y,'texture_size':SIZE,'eyes':[]}
    for label,center in EYES:
        domain=[center-0.10,0.065,0.20,0.17] # x minimum, z minimum, width, height
        uv_grid=np.zeros((SIZE,SIZE,2),dtype=np.float32)
        valid=np.zeros((SIZE,SIZE),dtype=bool)
        for row in range(SIZE):
            z=domain[1]+(row+0.5)/SIZE*domain[3]
            for col in range(SIZE):
                x=domain[0]+(col+0.5)/SIZE*domain[2]
                hit,co,normal,face=obj.ray_cast(inverse@Vector((x,-1.2,z)),direction,distance=2)
                if not hit:continue
                if face not in cache:
                    polygon=mesh.polygons[face]
                    cache[face]=([mesh.vertices[i].co.copy() for i in polygon.vertices],
                                 [Vector((*uv_layer.data[i].uv,0)) for i in polygon.loop_indices])
                triangle,texture_uv=cache[face]
                uv=barycentric_transform(co,*triangle,*texture_uv)
                uv_grid[row,col]=uv.x,uv.y
                valid[row,col]=True
        base=sample(source_base,uv_grid);mr=sample(source_mr,uv_grid)
        x=domain[0]+(np.arange(SIZE)+0.5)/SIZE*domain[2]
        z=domain[1]+(np.arange(SIZE)+0.5)/SIZE*domain[3]
        # Keep the socket rim, lash line and surrounding stickers anchored.
        radius=np.sqrt(((x[None,:]-center)/0.078)**2+((z[:,None]-0.149)/0.050)**2)
        mask=np.clip((1-radius)/0.20,0,1)
        mask=mask*mask*(3-2*mask)
        mask*=valid
        rgba=np.ones((SIZE,SIZE,4),dtype=np.float32);rgba[:,:,:3]=mask[:,:,None]
        image_file(f'{label}-base',base)
        image_file(f'{label}-mr',mr,'Non-Color')
        image_file(f'{label}-mask',rgba,'Non-Color')
        config['eyes'].append({'label':label,'domain':domain,
                               'base':f'/models/avatar-eye-prototype/{label}-base.png',
                               'mr':f'/models/avatar-eye-prototype/{label}-mr.png',
                               'mask':f'/models/avatar-eye-prototype/{label}-mask.png'})
        print('BAKED_EYE',label,flush=True)
    (ASSETS/'config.json').write_text(json.dumps(config,indent=2)+'\n')


def smooth(value):
    value=np.clip(value,0,1)
    return value*value*(3-2*value)


def bake_normal_fields(obj,config,scene):
    original=obj.data.materials[0]
    temporary=original.copy();obj.data.materials[0]=temporary
    nodes=temporary.node_tree.nodes;links=temporary.node_tree.links
    shader=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    normal=shader.inputs['Normal'].links[0].from_socket
    scale=nodes.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs['Scale'].default_value=0.5
    links.new(normal,scale.inputs[0])
    add=nodes.new('ShaderNodeVectorMath');add.operation='ADD';add.inputs[1].default_value=(0.5,0.5,0.5)
    links.new(scale.outputs[0],add.inputs[0])
    emission=nodes.new('ShaderNodeEmission');links.new(add.outputs[0],emission.inputs['Color'])
    output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL');links.new(emission.outputs[0],output.inputs['Surface'])
    camera=scene.camera
    saved=(scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y,scene.render.image_settings.file_format)
    scene.render.resolution_x=SIZE;scene.render.resolution_y=SIZE
    scene.render.image_settings.file_format='OPEN_EXR'
    for eye in config['eyes']:
        x0,z0,width,height=eye['domain'];cx=x0+width/2;cz=z0+height/2
        camera.location=(cx,-4,cz);camera.rotation_euler=(math.pi/2,0,0);camera.data.ortho_scale=width
        camera.data.sensor_fit='HORIZONTAL'
        scene.render.pixel_aspect_x=width/height;scene.render.pixel_aspect_y=1
        path=OUT/f"{eye['label']}-normal-raw.exr";scene.render.filepath=str(path)
        bpy.ops.render.render(write_still=True)
        loaded=bpy.data.images.load(str(path),check_existing=False)
        image_file(f"{eye['label']}-normal",pixels(loaded),'Non-Color')
        bpy.data.images.remove(loaded)
        eye['normal']=f"/models/avatar-eye-prototype/{eye['label']}-normal.png"
    scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y,scene.render.image_settings.file_format=saved
    obj.data.materials[0]=original;bpy.data.materials.remove(temporary)
    (ASSETS/'config.json').write_text(json.dumps(config,indent=2)+'\n')


def prototype_material(obj,config):
    mesh=obj.data
    original=mesh.materials[0].copy();original.name='UnmodifiedSourceForNeutralExport'
    material=mesh.materials[0];material.name='EyePrototype_CustomShader_NotGLTFPortable'
    tree=material.node_tree;nodes=tree.nodes;links=tree.links
    shader=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    base=shader.inputs['Base Color'].links[0].from_socket
    mr_image=upstream_image(shader.inputs['Roughness'])
    mr=next(n for n in nodes if n.type=='TEX_IMAGE' and n.image==mr_image).outputs['Color']
    original_normal=shader.inputs['Normal'].links[0].from_socket
    coordinates=np.empty(len(mesh.vertices)*3,dtype=np.float32)
    mesh.vertices.foreach_get('co',coordinates)
    matrix=np.array(obj.matrix_world)
    coordinates=coordinates.reshape(-1,3)@matrix[:3,:3].T+matrix[:3,3]
    loop_indices=np.empty(len(mesh.loops),dtype=np.int32);mesh.loops.foreach_get('vertex_index',loop_indices)
    original_uv=mesh.uv_layers.active
    attribute=mesh.attributes.new('EyePrototypeFrontMask','FLOAT','POINT')
    front=smooth((-coordinates[:,1]-0.24)/0.05)*(1-smooth((-coordinates[:,1]-0.40)/0.05))
    attribute.data.foreach_set('value',front.astype(np.float32))
    front_node=nodes.new('ShaderNodeAttribute');front_node.attribute_name=attribute.name
    def vector(operation,a,b=None,value=None):
        node=nodes.new('ShaderNodeVectorMath');node.operation=operation
        if a is not None:links.new(a,node.inputs[0])
        if b is not None:links.new(b,node.inputs[1])
        if value is not None:node.inputs[1].default_value=value
        return node.outputs[0]
    def image_node(image,uv):
        node=nodes.new('ShaderNodeTexImage');node.image=image;node.extension='CLIP';node.interpolation='Linear'
        links.new(uv,node.inputs['Vector'])
        return node.outputs['Color']
    controls={}
    head_yaw=nodes.new('ShaderNodeValue');head_yaw.name='HeadYawNormalAlignment';head_yaw.label='World head yaw for prototype normals (radians)'
    driver=head_yaw.outputs[0].driver_add('default_value').driver
    driver.type='SCRIPTED';driver.expression='head_yaw'
    variable=driver.variables.new();variable.name='head_yaw';variable.type='TRANSFORMS'
    variable.targets[0].id=obj.find_armature();variable.targets[0].bone_target='head'
    variable.targets[0].transform_type='ROT_Z';variable.targets[0].transform_space='WORLD_SPACE'
    variable.targets[0].rotation_mode='XYZ'
    controls['head-yaw']=head_yaw
    for eye in config['eyes']:
        label=eye['label'];domain=eye['domain']
        uv=mesh.uv_layers.new(name=f'EyeProjection_{label}')
        values=np.column_stack(((coordinates[:,0]-domain[0])/domain[2],(coordinates[:,2]-domain[1])/domain[3]))
        uv.data.foreach_set('uv',values[loop_indices].astype(np.float32).ravel())
        uv_node=nodes.new('ShaderNodeUVMap');uv_node.uv_map=uv.name
        uv_socket=uv_node.outputs['UV']
        textures={}
        for role in ['base','mr','mask','normal']:
            image=bpy.data.images.load(str(ASSETS/f'{label}-{role}.png'),check_existing=True)
            image.colorspace_settings.name='sRGB' if role=='base' else 'Non-Color';image.pack();textures[role]=image
        mask=image_node(textures['mask'],uv_socket)
        multiply=nodes.new('ShaderNodeMath');multiply.operation='MULTIPLY'
        links.new(mask,multiply.inputs[0]);links.new(front_node.outputs['Fac'],multiply.inputs[1])
        mask=multiply.outputs[0]
        combine=nodes.new('ShaderNodeCombineXYZ')
        controls[label]=[]
        absolute=[]
        for axis,amplitude,dimension in [('X',RANGE_X,domain[2]),('Y',RANGE_Y,domain[3])]:
            control=nodes.new('ShaderNodeValue');control.name=f'Gaze_{label}_{axis}';control.label=f'{label} gaze {axis} (-1..1)'
            control.outputs[0].default_value=0;controls[label].append(control)
            ab=nodes.new('ShaderNodeMath');ab.operation='ABSOLUTE';links.new(control.outputs[0],ab.inputs[0]);absolute.append(ab.outputs[0])
            scale=nodes.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=amplitude/dimension
            links.new(control.outputs[0],scale.inputs[0]);links.new(scale.outputs[0],combine.inputs[axis])
        scale=nodes.new('ShaderNodeVectorMath');scale.operation='SCALE'
        links.new(combine.outputs[0],scale.inputs[0]);links.new(mask,scale.inputs['Scale'])
        shifted=vector('SUBTRACT',uv_socket,scale.outputs[0])
        activation=nodes.new('ShaderNodeMath');activation.operation='MAXIMUM';links.new(absolute[0],activation.inputs[0]);links.new(absolute[1],activation.inputs[1])
        ramp=nodes.new('ShaderNodeMapRange');ramp.interpolation_type='SMOOTHSTEP'
        ramp.inputs['From Min'].default_value=0;ramp.inputs['From Max'].default_value=0.125
        links.new(activation.outputs[0],ramp.inputs['Value'])
        # Wider replacement support removes the original iris shading instead
        # of leaving a faint second rim where the displacement field tapers.
        support=nodes.new('ShaderNodeMapRange');support.interpolation_type='SMOOTHSTEP'
        support.inputs['From Min'].default_value=0;support.inputs['From Max'].default_value=0.1
        links.new(mask,support.inputs['Value'])
        weight=nodes.new('ShaderNodeMath');weight.operation='MULTIPLY';links.new(support.outputs['Result'],weight.inputs[0]);links.new(ramp.outputs['Result'],weight.inputs[1])
        for role in ['base','mr']:
            blend=nodes.new('ShaderNodeMixRGB');blend.blend_type='MIX'
            links.new(weight.outputs[0],blend.inputs[0]);links.new(base if role=='base' else mr,blend.inputs[1]);links.new(image_node(textures[role],shifted),blend.inputs[2])
            if role=='base':base=blend.outputs[0]
            else:mr=blend.outputs[0]
        decoded=vector('MULTIPLY',image_node(textures['normal'],shifted),value=(2,2,2))
        decoded=vector('ADD',decoded,value=(-1,-1,-1))
        rotate=nodes.new('ShaderNodeVectorRotate');rotate.rotation_type='AXIS_ANGLE';rotate.inputs['Axis'].default_value=(0,0,1)
        links.new(decoded,rotate.inputs['Vector']);links.new(head_yaw.outputs[0],rotate.inputs['Angle'])
        normal_blend=nodes.new('ShaderNodeMixRGB');links.new(weight.outputs[0],normal_blend.inputs[0]);links.new(original_normal,normal_blend.inputs[1]);links.new(rotate.outputs[0],normal_blend.inputs[2])
        original_normal=normal_blend.outputs[0]
    mesh.uv_layers.active=original_uv;original_uv.active_render=True
    links.new(base,shader.inputs['Base Color'])
    separate=nodes.new('ShaderNodeSeparateColor');links.new(mr,separate.inputs['Color'])
    links.new(separate.outputs['Green'],shader.inputs['Roughness'])
    links.new(separate.outputs['Blue'],shader.inputs['Metallic'])
    links.new(original_normal,shader.inputs['Normal'])
    material['prototype_gaze_range_x']=RANGE_X;material['prototype_gaze_range_y']=RANGE_Y
    material['export_warning']='Custom shader eye motion requires the separate R3F shader. Neutral GLB export intentionally uses the original material.'
    return original,controls


def build(obj,rig):
    config=json.loads((ASSETS/'config.json').read_text())
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE'
    scene.render.resolution_x=800;scene.render.resolution_y=600;scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2
    if hasattr(scene.eevee,'taa_render_samples'):scene.eevee.taa_render_samples=24
    scene.world=bpy.data.worlds.new('EyePrototypeWorld');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.72,0.70,0.74,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.7
    scene.view_settings.view_transform='Standard'
    for location,energy,size in [((-3,-4,4),220,4),((3,-2,1),100,3)]:
        bpy.ops.object.light_add(type='AREA',location=location)
        light=bpy.context.object;light.data.energy=energy;light.data.shape='DISK';light.data.size=size
        light.rotation_euler=(Vector((0,0,0.2))-light.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add();scene.camera=bpy.context.object;scene.camera.data.type='ORTHO'
    preview.OUT=OUT
    def capture(name,yaw=0):
        preview.pose(rig,yaw)
        return render_eye(name,yaw)
    def render_eye(name,yaw):
        camera=scene.camera;camera.location=(0,-4,0.15)
        camera.rotation_euler=(Vector((0,0,0.15))-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.ortho_scale=0.55;camera.data.clip_start=0.01
        scene.render.filepath=str(OUT/f'{name}.png');bpy.ops.render.render(write_still=True)
        return str(Path(scene.render.filepath).relative_to(ROOT))
    capture('source-neutral-reference')
    bake_normal_fields(obj,config,scene)
    original,controls=prototype_material(obj,config)
    results=[]
    poses=[('neutral',(0,0),(0,0),0),('left',(-1,0),(-1,0),0),('right',(1,0),(1,0),0),
           ('up',(0,1),(0,1),0),('down',(0,-1),(0,-1),0),
           ('diagonal-up-right',(1,1),(1,1),0),('diagonal-down-left',(-1,-1),(-1,-1),0),
           ('independent',(-1,0),(1,0),0),('head-left-gaze-right',(1,0),(1,0),-25),
           ('head-right-gaze-left',(-1,0),(-1,0),25)]
    for name,left,right,yaw in poses:
        for label,gaze in zip([e[0] for e in EYES],[left,right]):
            for node,value in zip(controls[label],gaze):node.outputs[0].default_value=value
        results.append({'name':name,'left':left,'right':right,'head_yaw':yaw,'preview':capture(name,yaw)})
        if '--quick' in sys.argv and len(results)==3:break
    for label,_ in EYES:
        for node in controls[label]:node.outputs[0].default_value=0
    preview.pose(rig)
    scene['eye_prototype_instructions']='Select the avatar material. Set Gaze_viewer-left/right_X/Y Value nodes independently in -1..1. No blinking. Shader is NOT standard GLB portable.'
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(WORKING))
    # The exported neutral asset is deliberately ordinary glTF PBR. The custom
    # gaze effect lives in the .blend and the isolated R3F proof of concept.
    custom=obj.data.materials[0];obj.data.materials[0]=original
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);rig.select_set(True)
    bpy.context.view_layer.objects.active=rig
    bpy.ops.export_scene.gltf(filepath=str(NEUTRAL),export_format='GLB',use_selection=True,export_skins=True,export_animations=False,export_apply=False)
    obj.data.materials[0]=custom
    assert appearance_signature(SOURCE)==appearance_signature(NEUTRAL),'Neutral exported appearance changed'
    report={'range_x_model_units':RANGE_X,'range_y_model_units':RANGE_Y,'poses':results,
            'working_copy':str(WORKING.relative_to(ROOT)),'neutral_glb':str(NEUTRAL.relative_to(ROOT)),
            'export_compatibility':'Neutral GLB preserves ordinary PBR materials only. Dynamic eye shader is not exported; separate R3F shader required.',
            'normal_map':'Original eye shading normals baked into local world-normal fields, displaced with the artwork, and rotated with the head. All non-eye material regions retain original normal mapping.',
            'visual_review':'Pending; reject if double pupils, smearing, seams or altered identity are visible.'}
    reference=bpy.data.images.load(str(OUT/'source-neutral-reference.png'),check_existing=False)
    neutral=bpy.data.images.load(str(OUT/'neutral.png'),check_existing=False)
    # Compare encoded PNG samples in the same color space, not mixed image defaults.
    reference.colorspace_settings.name='Non-Color'
    neutral.colorspace_settings.name='Non-Color'
    difference=np.abs(pixels(reference)-pixels(neutral))
    report['neutral_image_comparison']={'max_channel_difference':float(difference.max()),'mean_channel_difference':float(difference.mean())}
    bpy.data.images.remove(reference);bpy.data.images.remove(neutral)
    (OUT/'prototype-report.json').write_text(json.dumps(report,indent=2)+'\n')


def main():
    protect()
    obj,rig=load()
    if '--bake' in sys.argv:bake(obj)
    else:build(obj,rig)
    protect()
    (OUT/'bake-status.json').write_text(json.dumps({'protected_inputs_unchanged':True,'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,1)},indent=2)+'\n')


if __name__=='__main__':main()
