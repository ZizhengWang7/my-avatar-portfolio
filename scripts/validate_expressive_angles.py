"""Read-only head-only pose sweep of the actual exported GLB, with small previews."""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Quaternion, Vector

ROOT = Path(__file__).resolve().parents[1]
ENVELOPE = '--envelope' in sys.argv
CONSERVATIVE = '--conservative' in sys.argv or ENVELOPE
PREFIX = 'avatar-expressive-envelope' if ENVELOPE else 'avatar-expressive-conservative' if CONSERVATIVE else 'avatar-expressive'
OUT = ROOT / f'reports/{PREFIX}-previews'
REPORT_PATH = ROOT / f'reports/{PREFIX}-validation.json'
MODELS = [ROOT / 'public/assets/人物3d建模.glb', ROOT / 'public/models/my-avatar-head-test.glb']


def contact_sheets():
    import numpy as np
    report = json.loads(REPORT_PATH.read_text())
    poses = report['poses']
    groups = [poses[:1], poses[1:5], poses[5:9], poses[9:13], poses[13:15], poses[15:19], poses[19:23]]
    if CONSERVATIVE:
        groups = [poses[:1]] + [poses[i:i+4] for i in range(1, len(poses), 4)]
    sheets = []
    for number, group in enumerate(groups):
        # Crop unused margins; retain head, neck, collar and upper shoulders.
        width, height = 400, 500
        pixels = np.zeros((len(group)*height, 3*width, 4), dtype=np.float32)
        for row, pose in enumerate(group):
            for col, filename in enumerate(pose['previews']):
                image = bpy.data.images.load(str(ROOT / filename), check_existing=False)
                raw = np.empty(480*560*4, dtype=np.float32)
                image.pixels.foreach_get(raw)
                tile = raw.reshape((560, 480, 4))[40:540, 40:440]
                target_row = len(group)-1-row
                pixels[target_row*height:(target_row+1)*height, col*width:(col+1)*width] = tile
                bpy.data.images.remove(image)
        sheet = bpy.data.images.new(f'Contact-{number}', width=3*width, height=len(group)*height, alpha=True)
        sheet.pixels.foreach_set(pixels.ravel())
        sheet.filepath_raw = str(OUT / f'contact-{number}.png')
        sheet.file_format = 'PNG'
        sheet.save()
        sheets.append({'path': str(Path(sheet.filepath_raw).relative_to(ROOT)), 'rows_top_to_bottom': [p['name'] for p in group], 'columns': ['front', 'quarter', 'side']})
        bpy.data.images.remove(sheet)
    report['contact_sheets'] = sheets
    REPORT_PATH.write_text(json.dumps(report, indent=2)+'\n')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in MODELS}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(MODELS[1]))
    rig = next(obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE')
    obj = next(obj for obj in bpy.context.scene.objects if obj.type == 'MESH')
    head = rig.pose.bones['head']
    rest = head.rotation_quaternion.copy()
    head.rotation_mode = 'QUATERNION'
    basis = (rig.matrix_world @ head.bone.matrix_local).to_quaternion()
    fixed = [v.index for v in obj.data.vertices if all(obj.vertex_groups[g.group].name != 'head' or g.weight == 0 for g in v.groups)]
    positions = [obj.matrix_world @ obj.data.vertices[i].co for i in fixed]
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x, scene.render.resolution_y = 480, 560
    scene.render.resolution_percentage = 100
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = False
    scene.display.shading.background_type = 'WORLD'
    scene.world = bpy.data.worlds.new('DiagnosticWorld')
    scene.world.color = (0.72, 0.67, 0.8)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 2.35
    scene.camera = camera
    poses = [('neutral', 0, 0, 0)]
    for angle in ([10, 15] if CONSERVATIVE else [20, 25, 30, 35]):
        for sign in [-1, 1]:
            poses.append((f'yaw-{sign*angle:+d}', sign*angle, 0, 0))
    for angle in ([10] if CONSERVATIVE else [15, 20]):
        for sign in [-1, 1]:
            poses.append((f'pitch-{sign*angle:+d}', 0, sign*angle, 0))
    for sign in [-1, 1]:
        poses.append((f'roll-{sign*5:+d}', 0, 0, sign*5))
    for yaw in ([-15, 15] if CONSERVATIVE else [-35, 35]):
        for pitch in ([-10, 10] if CONSERVATIVE else [-20, 20]):
            for roll in [-5, 5]:
                poses.append((f'corner-{yaw:+d}-{pitch:+d}-{roll:+d}', yaw, pitch, roll))
    if ENVELOPE:
        poses = []
        for yaw, pitch, roll in [(y, p, r) for y in [-1, 1] for p in [-1, 1] for r in [-1, 1]] + [(y, p, 0) for y in [-1, 1] for p in [-1, 1]] + [(y, 0, r) for y in [-1, 1] for r in [-1, 1]] + [(0, p, r) for p in [-1, 1] for r in [-1, 1]]:
            length = math.sqrt(yaw*yaw + pitch*pitch + roll*roll)
            poses.append((f'envelope-{yaw:+d}-{pitch:+d}-{roll:+d}', yaw*15/length, pitch*10/length, roll*5/length))
    checks = []
    for name, yaw, pitch, roll in poses:
        rotation = Quaternion((0, 0, 1), math.radians(yaw)) @ Quaternion((1, 0, 0), math.radians(pitch)) @ Quaternion((0, -1, 0), math.radians(roll))
        head.rotation_quaternion = rest @ basis.inverted() @ rotation @ basis
        bpy.context.view_layer.update()
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        error = max(((evaluated.matrix_world @ evaluated.data.vertices[i].co) - position).length for i, position in zip(fixed, positions))
        assert error < 1e-5, 'Torso vertices moved'
        files = []
        for view, location in [('front', (0, -4, 0)), ('quarter', (2.8, -3, 0)), ('side', (4, 0, 0))]:
            camera.location = location
            camera.rotation_euler = (Vector((0, 0, 0)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
            path = OUT / f'{name}-{view}.png'
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            files.append(str(path.relative_to(ROOT)))
        checks.append({'name': name, 'yaw': yaw, 'pitch': pitch, 'roll': roll, 'fixed_vertices_checked': len(fixed), 'max_fixed_displacement': error, 'previews': files})
    assert all(digest(ROOT / path) == value for path, value in hashes.items())
    report = {'model_hashes': hashes, 'models_unchanged': True,
              'animated_bones': ['head'], 'poses': checks,
              'preview_method': '480x560 textured Workbench, front/quarter/side; diagnostic geometry and texture review, not browser PBR lighting.',
              'visual_review': 'Pending; numeric stationary-torso checks alone do not establish safe angles.'}
    REPORT_PATH.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    if '--sheets-only' in sys.argv:
        contact_sheets()
    else:
        main()
        contact_sheets()
