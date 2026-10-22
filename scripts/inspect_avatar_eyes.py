"""Read-only eye-rig feasibility inspection. No geometry, rig, or asset saves.

Imports one GLB; writes only diagnostic renders and JSON under reports/.
Camera clipping and temporary display overrides reveal surfaces without cuts.
"""
import hashlib
import json
from pathlib import Path
import resource
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import barycentric_transform

sys.path.insert(0,str(Path(__file__).resolve().parent))
from inspect_avatar import Components

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'public/models/my-avatar-head-refined.glb'
OUT=ROOT/'reports/avatar-eye-inspection'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def render(scene,name,location,target,scale=0.75,clip=None):
    camera=scene.camera
    camera.location=location
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=scale
    camera.data.clip_start=clip if clip is not None else 0.01
    scene.render.filepath=str(OUT/f'{name}.png')
    bpy.ops.render.render(write_still=True)
    camera.data.clip_start=0.01
    return str(Path(scene.render.filepath).relative_to(ROOT))


def analyze_geometry(obj):
    mesh=obj.data
    world=obj.matrix_world
    inverse=world.inverted()
    direction=(inverse.to_3x3()@Vector((0,1,0))).normalized()
    shader=next(n for n in mesh.materials[0].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    image=shader.inputs['Base Color'].links[0].from_node.image
    pixels=np.empty(len(image.pixels),dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels=pixels.reshape(image.size[1],image.size[0],4)
    uv=mesh.uv_layers.active
    def ray(x,z):
        origin=inverse@Vector((x,-1.2,z))
        hits=[]
        for step in range(12):
            hit,co,normal,face=obj.ray_cast(origin,direction,distance=3)
            if not hit:break
            point=world@co
            if point.y>0.25:break
            polygon=mesh.polygons[face]
            ids=polygon.vertices
            loops=polygon.loop_indices
            texture_uv=barycentric_transform(co,*(mesh.vertices[i].co for i in ids[:3]),
                                              *(Vector((*uv.data[i].uv,0)) for i in loops[:3]))
            u,v=texture_uv.x,texture_uv.y
            pixel=pixels[min(image.size[1]-1,max(0,int(v*image.size[1]))),min(image.size[0]-1,max(0,int(u*image.size[0])))]
            hits.append({'y':point.y,'face':face,'uv':[u,v],'rgb':[float(c) for c in pixel[:3]], 'normal':list((world.to_3x3()@normal).normalized())})
            origin=co+direction*0.00002
        return hits
    components=Components(len(mesh.vertices))
    for edge in mesh.edges:components.join(*edge.vertices)
    physical_roots={components.find(v.index) for v in mesh.vertices}
    # Keep compact root IDs before virtual seam adjacency is added.
    physical=np.array([components.find(v.index) for v in mesh.vertices],dtype=np.uint32)
    coincident={}
    for vertex in mesh.vertices:
        key=tuple(round(c/2e-7) for c in vertex.co)
        if key in coincident:components.join(vertex.index,coincident[key])
        else:coincident[key]=vertex.index
    del coincident
    virtual_roots={components.find(v.index) for v in mesh.vertices}
    results=[];grid=[]
    for name,sign in [('viewer-left',-1),('viewer-right',1)]:
        center=sign*0.145
        samples=[];faces=set()
        for x in np.linspace(center-0.065,center+0.065,25):
            for z in np.linspace(0.11,0.19,21):
                if ((x-center)/0.065)**2+((z-0.15)/0.04)**2>0.8:continue
                hits=ray(float(x),float(z))
                if hits:
                    samples.append({'x':float(x),'z':float(z),'hits':hits})
                    faces.add(hits[0]['face'])
        visible_vertices={i for face in faces for i in mesh.polygons[face].vertices}
        chart_ids={int(physical[i]) for i in visible_vertices}
        depth=[s['hits'][0]['y'] for s in samples]
        front_counts=[sum(h['y']<0 for h in s['hits']) for s in samples]
        uvs=np.array([s['hits'][0]['uv'] for s in samples])
        results.append({'label':name,'sampling_center_xz':[center,0.15],
                        'sample_count':len(samples),'visible_faces_sampled':len(faces),
                        'physical_fragments_touched':len(chart_ids),
                        'virtual_components_touched':len({components.find(i) for i in visible_vertices}),
                        'front_y_range':[min(depth),max(depth)],
                        'front_half_surface_hit_count_histogram':{str(n):front_counts.count(n) for n in set(front_counts)},
                        'uv_bounds':{'min':uvs.min(axis=0).tolist(),'max':uvs.max(axis=0).tolist()},
                        'center_ray':ray(center,0.15),
                        'caveat':'Visible eye-region ellipse, not an anatomical boundary or a separation selection. Physical fragments are not necessarily UV charts.'})
        grid.extend({'eye':name,**sample} for sample in samples)
    # Diagnostic atlas copy with sampled eye UV points; no texture is edited.
    atlas=pixels[::2,::2].copy()
    for sample in grid:
        u,v=sample['hits'][0]['uv']
        x=min(atlas.shape[1]-3,max(3,int(u*atlas.shape[1])))
        y=min(atlas.shape[0]-3,max(3,int(v*atlas.shape[0])))
        atlas[y-2:y+3,x-2:x+3]=[1,0.1,0.15,1] if sample['eye']=='viewer-left' else [0.1,0.8,1,1]
    diagnostic=bpy.data.images.new('EyeUVScatterDiagnostic',width=atlas.shape[1],height=atlas.shape[0],alpha=True)
    diagnostic.pixels.foreach_set(atlas.ravel())
    diagnostic.filepath_raw=str(OUT/'eye-uv-atlas-samples.png');diagnostic.file_format='PNG';diagnostic.save()
    bpy.data.images.remove(diagnostic)
    (OUT/'eye-ray-samples.json').write_text(json.dumps(grid,indent=2)+'\n')
    return {'physical_component_count':len(physical_roots),'virtual_component_count':len(virtual_roots),
            'virtual_coincidence_cell_local_units':2e-7,'eye_regions':results,
            'method':'Front-to-back rays through two conservative visible-eye ellipses; up to 12 hits per ray before world Y=0.25. Eye whites/iris are not semantically segmented. UVs sampled barycentrically from actual exported triangles.',
            'coordinate_system':'Blender world Z up; camera looks along +Y, so front surfaces have negative Y.',
            'base_color_image':image.name,'base_color_image_size':list(image.size)}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    protected=[p for folder in ['src','backups','public/models'] for p in (ROOT/folder).rglob('*') if p.is_file()]
    protected+=[p for p in (ROOT/'reports').glob('*.blend')]
    protected+=[ROOT/'public/assets/人物3d建模.glb']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in protected}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(MODEL))
    obj=next(o for o in bpy.context.scene.objects if o.type=='MESH')
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    scene=bpy.context.scene
    scene.render.engine='BLENDER_WORKBENCH'
    scene.render.resolution_x=800;scene.render.resolution_y=600
    scene.render.resolution_percentage=100
    scene.render.threads_mode='FIXED';scene.render.threads=2
    scene.display.shading.color_type='TEXTURE'
    scene.display.shading.light='STUDIO'
    scene.display.shading.show_shadows=True
    scene.display.shading.background_type='WORLD'
    scene.world=bpy.data.worlds.new('EyeDiagnosticWorld');scene.world.color=(0.72,0.67,0.8)
    scene.view_settings.view_transform='Standard'
    bpy.ops.object.camera_add();scene.camera=bpy.context.object
    scene.camera.data.type='ORTHO'
    files=[]
    files.append(render(scene,'eyes-front',(0,-4,0.28),(0,0,0.28),0.72))
    files.append(render(scene,'eyes-quarter-positive-x',(2.4,-4,0.28),(0,0,0.28),0.72))
    files.append(render(scene,'eyes-quarter-negative-x',(-2.4,-4,0.28),(0,0,0.28),0.72))
    files.append(render(scene,'eye-positive-x-profile',(4,-0.1,0.28),(0,-0.1,0.28),0.55))
    scene.display.shading.light='FLAT'
    files.append(render(scene,'eyes-base-color-only',(0,-4,0.28),(0,0,0.28),0.72))
    scene.display.shading.light='STUDIO'
    scene.display.shading.color_type='SINGLE'
    scene.display.shading.single_color=(0.65,0.65,0.65)
    files.append(render(scene,'eyes-untextured-clay',(0,-4,0.28),(0,0,0.28),0.72))
    files.append(render(scene,'eye-profile-untextured-clay',(4,-0.1,0.28),(0,-0.1,0.28),0.55))
    files.append(render(scene,'eyes-untextured-detail',(0,-4,0.15),(0,0,0.15),0.54))
    scene.display.shading.color_type='TEXTURE'
    for y in [-0.45,-0.38,-0.30,-0.22]:
        files.append(render(scene,f'camera-cut-y{y:.2f}',(0,-4,0.28),(0,0,0.28),0.72,4+y))
    # Tighter eye views and cut levels across the measured front-surface depth.
    for sign in [-1,1]:
        x=sign*0.145
        files.append(render(scene,f'eye-{sign:+d}-close',(x,-4,0.15),(x,0,0.15),0.24))
        files.append(render(scene,f'eye-{sign:+d}-oblique',(sign*2,-4,0.15),(x,-0.34,0.15),0.28))
    for y in [-0.36,-0.34,-0.32]:
        files.append(render(scene,f'eye-cut-y{y:.2f}',(0,-4,0.15),(0,0,0.15),0.54,4+y))
    geometry=analyze_geometry(obj)
    report={'model':str(MODEL.relative_to(ROOT)),
            'objects':[{'name':o.name,'type':o.type} for o in bpy.context.scene.objects if o!=scene.camera],
            'bones':[b.name for b in rig.data.bones],
            'shape_keys':[k.name for k in obj.data.shape_keys.key_blocks] if obj.data.shape_keys else [],
            'vertices':len(obj.data.vertices),'faces':len(obj.data.polygons),
            'materials':[m.name for m in obj.data.materials],
            'images':[{'name':i.name,'size':list(i.size)} for i in bpy.data.images],
            'previews':files,'protected_hashes':hashes,'geometry_analysis':geometry}
    report['protected_files_unchanged']=all(digest(ROOT/p)==h for p,h in hashes.items())
    report['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1048576,1)
    (OUT/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
