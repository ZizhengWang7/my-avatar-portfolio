"""Read-only previews of actual poses sampled from the JavaScript motion tests."""
import json
import math
from pathlib import Path
import sys

import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refine_avatar_head as preview

preview.OUT=ROOT/'reports/refined-avatar-integration-previews'
preview.OUT.mkdir(parents=True,exist_ok=True)
report=json.loads((ROOT/'reports/refined-avatar-motion-tests.json').read_text())
samples=report['selectedPoses']
selected=[{'name':'neutral','yaw':0,'pitch':0,'roll':0}]
for axis in ['yaw','pitch','roll']:
    pose=max(samples,key=lambda p:abs(p[axis]))
    selected.append({**pose,'name':f'{axis}-peak'})
    if axis=='yaw':selected.append({'name':'yaw-peak-mirrored','yaw':-pose['yaw'],'pitch':pose['pitch'],'roll':-pose['roll']})
selected.append(next(p for p in samples if p['name']=='corner_holds_yaw_peak'))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT/'public/models/my-avatar-head-refined.glb'))
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
for bone in rig.pose.bones:bone.rotation_mode='QUATERNION'
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=520;scene.render.resolution_y=620
scene.render.resolution_percentage=100
scene.render.threads_mode='FIXED';scene.render.threads=2
scene.display.shading.color_type='TEXTURE';scene.display.shading.light='STUDIO'
scene.display.shading.show_shadows=True;scene.display.shading.background_type='WORLD'
scene.world=bpy.data.worlds.new('MotionPreviewWorld');scene.world.color=(0.72,0.67,0.8)
scene.view_settings.view_transform='Standard'
bpy.ops.object.camera_add();scene.camera=bpy.context.object;scene.camera.data.type='ORTHO'
for sample in selected:
    preview.pose(rig,*[math.degrees(sample[key]) for key in ['yaw','pitch','roll']])
    sample['previews']=[preview.render(scene,sample['name'],view) for view in ['front','quarter','side']]
    sample['previews'].append(preview.render(scene,sample['name'],'side',True))
(preview.OUT/'poses.json').write_text(json.dumps(selected,indent=2)+'\n')
