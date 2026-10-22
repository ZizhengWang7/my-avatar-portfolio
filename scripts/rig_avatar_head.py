"""Conservative head-only prototype; never exports to the source path.

First run with -- --inspect-only and inspect the front/side previews. Then run
without that flag only after confirming the proposed transition misses clothing.
Workbench texture previews are diagnostic, not final PBR appearance previews.
"""
import hashlib
from array import array
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'public/assets/人物3d建模.glb'
REPORT = ROOT / 'reports/avatar-inspection.json'
OUTPUT = ROOT / 'public/models/my-avatar-head-test.glb'
WORKING = ROOT / 'reports/my-avatar-head-prototype.blend'
PREVIEWS = ROOT / 'reports/avatar-head-previews'
RESULT = ROOT / 'reports/avatar-head-rig-report.json'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def aim(obj, point):
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def render(scene, camera, name, position):
    camera.location = position
    aim(camera, (0, 0, 0))
    scene.render.filepath = str(PREVIEWS / (name + '.png'))
    bpy.ops.render.render(write_still=True)


def smoothstep(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def geometry_digest(mesh):
    h = hashlib.sha256()
    for vertex in mesh.vertices:
        h.update(struct.pack('<3f', *vertex.co))
    for layer in mesh.uv_layers:
        data = array('f', [0]) * (len(layer.data) * 2)
        layer.data.foreach_get('uv', data)
        h.update(data.tobytes())
    return h.hexdigest()


def read_glb(path):
    with path.open('rb') as stream:
        header = stream.read(20)
        size, kind = struct.unpack_from('<II', header, 12)
        if kind != 0x4e4f534a:
            raise RuntimeError('Missing GLB JSON chunk')
        return json.loads(stream.read(size))


def appearance_signature(path):
    data = path.read_bytes()
    size = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20+size])
    binary_start = 28 + size
    def texture(info):
        tex = gltf['textures'][info['index']]
        image = gltf['images'][tex['source']]
        view = gltf['bufferViews'][image['bufferView']]
        offset = binary_start + view.get('byteOffset', 0)
        sampler = gltf.get('samplers', [])[tex['sampler']] if 'sampler' in tex else {}
        return {
            'payload_sha256': hashlib.sha256(data[offset:offset+view['byteLength']]).hexdigest(),
            'uv_set': info.get('texCoord', 0),
            'sampler': {key: sampler.get(key, default) for key, default in
                        [('magFilter', 9729), ('minFilter', 9987), ('wrapS', 10497), ('wrapT', 10497)]},
        }
    signatures = []
    for mat in gltf['materials']:
        pbr = mat['pbrMetallicRoughness']
        signatures.append({
            'base_color': pbr.get('baseColorFactor', [1, 1, 1, 1]),
            'metallic': pbr.get('metallicFactor', 1),
            'roughness': pbr.get('roughnessFactor', 1),
            'double_sided': mat.get('doubleSided', False),
            'alpha_mode': mat.get('alphaMode', 'OPAQUE'),
            'base_texture': texture(pbr['baseColorTexture']),
            'roughness_texture': texture(pbr['metallicRoughnessTexture']),
            'normal_texture': texture(mat['normalTexture']),
            'normal_scale': mat['normalTexture'].get('scale', 1),
        })
    return signatures


def main():
    original_hash = digest(SOURCE)
    inspection = json.loads(REPORT.read_text())
    if original_hash != inspection['source_sha256_after']:
        raise RuntimeError('Source differs from Phase 1; repeat inspection first.')
    if SOURCE.resolve() == OUTPUT.resolve():
        raise RuntimeError('Output must never overwrite original.')
    if '--validate-existing' in sys.argv:
        result = json.loads(RESULT.read_text())
        same = appearance_signature(SOURCE) == appearance_signature(OUTPUT)
        assert same, 'Exported material or texture payload changed'
        result['export_validation']['material_semantics_and_texture_payloads_identical'] = same
        result['source_unchanged'] = original_hash == result['source_sha256']
        RESULT.write_text(json.dumps(result, indent=2) + '\n')
        print('APPEARANCE_VALIDATED', same)
        return
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if len(meshes) != 1:
        raise RuntimeError('Expected the single Phase 1 mesh; stopping.')
    obj = meshes[0]
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 400
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 2
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.color_type = 'TEXTURE'
    shading.show_shadows = True
    shading.show_cavity = False
    shading.background_type = 'WORLD'
    scene.world = scene.world or bpy.data.worlds.new('PreviewWorld')
    scene.world.color = (0.72, 0.67, 0.8)
    scene.view_settings.view_transform = 'Standard'
    bpy.ops.object.camera_add(location=(0, -4, 0))
    camera = bpy.context.object
    camera.name = 'InspectionCamera'
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 2.35
    scene.camera = camera

    if '--inspect-only' in sys.argv:
        render(scene, camera, 'boundary-front-negative-y', (0, -4, 0))
        render(scene, camera, 'boundary-front-positive-y', (0, 4, 0))
        render(scene, camera, 'boundary-side', (4, 0, 0))
        assert digest(SOURCE) == original_hash
        return

    # Phase 1's narrowest band (-0.24 .. -0.16) was checked in front/side
    # previews. Keep shoulders/collar below the transition stationary, and
    # protect the forward chin from the height-only neck blend.
    profile = inspection['meshes'][0]['vertical_profile_24_bands']
    neck_band = min((band for band in profile if 0.33 < band['height_fraction'][0] < 0.46),
                    key=lambda band: band['world_bounds']['max'][0] - band['world_bounds']['min'][0])
    neck_bounds = neck_band['world_bounds']
    if not (-0.27 < neck_bounds['min'][2] < -0.18):
        raise RuntimeError('Unexpected neck profile; stop for boundary review.')
    bottom, top = -0.24, -0.12
    before = geometry_digest(obj.data)
    material_names = [slot.material.name for slot in obj.material_slots]
    mesh_world = obj.matrix_world.copy()
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.object.armature_add(location=(0, 0, 0))
    rig = bpy.context.object
    rig.name = 'AvatarHeadPrototype'
    rig.show_in_front = True
    bpy.ops.object.mode_set(mode='EDIT')
    bones = rig.data.edit_bones
    bones.remove(bones[0])
    torso = bones.new('torso')
    torso.head, torso.tail = (0, 0.12, -0.85), (0, 0.12, bottom)
    neck = bones.new('neck')
    neck.head, neck.tail, neck.parent = torso.tail, (0, 0.12, -0.10), torso
    neck.use_connect = True
    head = bones.new('head')
    head.head, head.tail, head.parent = neck.tail, (0, 0.12, 0.65), neck
    head.use_connect = True
    bpy.ops.object.mode_set(mode='OBJECT')
    groups = {name: obj.vertex_groups.new(name=name) for name in ('torso', 'neck', 'head')}
    torso_indices = []
    head_indices = []
    transition_vertices = 0
    weight_summary = {'fixed_torso_vertices': 0, 'rigid_head_vertices': 0, 'blend_vertices': 0}
    for vertex in obj.data.vertices:
        position = mesh_world @ vertex.co
        t = smoothstep((position.z - bottom) / (top - bottom))
        chin = smoothstep((-position.y - 0.18) / 0.12) * smoothstep((position.z + 0.31) / 0.055)
        t = max(t, chin)
        if t == 0:
            torso_indices.append(vertex.index)
        elif t == 1:
            head_indices.append(vertex.index)
        else:
            weights = ((1-t)**2, 2*t*(1-t), t*t)
            for name, weight in zip(('torso', 'neck', 'head'), weights):
                groups[name].add([vertex.index], weight, 'REPLACE')
            transition_vertices += 1
    # Batch rigid groups instead of issuing hundreds of thousands of operators.
    groups['torso'].add(torso_indices, 1.0, 'REPLACE')
    groups['head'].add(head_indices, 1.0, 'REPLACE')
    weight_summary.update(fixed_torso_vertices=len(torso_indices), rigid_head_vertices=len(head_indices), blend_vertices=transition_vertices)
    obj.parent = rig
    obj.matrix_world = mesh_world
    modifier = obj.modifiers.new('HeadPrototypeSkin', 'ARMATURE')
    modifier.object = rig
    # Linear skinning matches glTF; don't rely on Blender-only preserve-volume.
    modifier.use_deform_preserve_volume = False
    for bone in rig.pose.bones:
        bone.rotation_mode = 'QUATERNION'

    # No evaluated mesh copies: read a few evaluated vertices through the
    # dependency graph. Original mesh coordinates and UVs remain unchanged.
    fixed_samples = torso_indices
    head_samples = head_indices[::max(1, len(head_indices)//500)]
    from mathutils import Quaternion
    def pose(yaw, pitch):
        # World Z yaw; world X pitch. Convert each into its bone's local frame.
        for name, ratio in [('neck', 0.3), ('head', 0.7)]:
            bone = rig.pose.bones[name]
            rotation = Quaternion((0, 0, 1), math.radians(yaw)*ratio) @ Quaternion((1, 0, 0), math.radians(pitch)*ratio)
            basis = bone.bone.matrix_local.to_quaternion()
            bone.rotation_quaternion = basis.inverted() @ rotation @ basis
        bpy.context.view_layer.update()

    checks = []
    for name, yaw, pitch in [('neutral', 0, 0), ('left-15', -15, 0), ('right-15', 15, 0), ('up-10', 0, -10), ('down-10', 0, 10)]:
        pose(yaw, pitch)
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        def displacement(indices):
            return max(((evaluated.matrix_world @ evaluated.data.vertices[i].co) - (mesh_world @ obj.data.vertices[i].co)).length for i in indices)
        fixed_error = displacement(fixed_samples)
        moved = displacement(head_samples)
        checks.append({'pose': name, 'yaw_degrees': yaw, 'pitch_degrees': pitch, 'fixed_torso_max_sample_displacement': fixed_error, 'head_max_sample_displacement': moved, 'fixed_samples': len(fixed_samples)})
        if fixed_error > 1e-5:
            raise RuntimeError('Torso moved; aborting export.')
        if (yaw or pitch) and moved < 0.01:
            raise RuntimeError('Head did not move; aborting export.')
        render(scene, camera, name, (0, -4, 0))
        if name in ('up-10', 'down-10'):
            render(scene, camera, name + '-side', (4, 0, 0))
    pose(0, 0)
    camera.location = (0, -4, 0)
    aim(camera, (0, 0, 0))
    assert before == geometry_digest(obj.data), 'Original geometry/UV data changed'
    assert material_names == [slot.material.name for slot in obj.material_slots]
    assert original_hash == digest(SOURCE), 'Source changed'
    # Avoid accumulating large .blend1 backups during prototype reruns.
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(WORKING))
    # Export requires a separate --export-reviewed run after pose preview review.
    result = {
        'source_sha256': original_hash, 'source_unchanged': True,
        'working_copy': str(WORKING), 'neutral_geometry_uv_digest_unchanged': True,
        'neck_band_from_phase1': neck_band,
        'weight_transition_world_z': [bottom, top],
        'chin_protection': 'Forward-facing chin below the upper neck band receives extra head influence; geometry heuristic, not a semantic segmentation.',
        'weights': weight_summary, 'pose_checks': checks,
        'preview_renderer': 'Workbench textured studio, 400x480. Not a PBR appearance validation.',
        'visual_review': 'Front and side neutral/posed previews reviewed: head motion is visible, shoulders/collar appear stable, no obvious tearing at tested angles. Existing faceting and texture artifacts remain. Close-up PBR and continuous-motion validation still required.',
        'exported': False,
    }
    if '--export-reviewed' in sys.argv:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=str(OUTPUT), export_format='GLB', use_selection=True,
                                  export_skins=True, export_animations=False, export_apply=False)
        gltf = read_glb(OUTPUT)
        source_gltf = read_glb(SOURCE)
        primitives = [p for mesh in gltf.get('meshes', []) for p in mesh['primitives']]
        skin = gltf.get('skins', [])
        joint_names = [gltf['nodes'][index].get('name') for index in skin[0]['joints']] if skin else []
        validation = {
            'skin_count': len(skin), 'joint_names': joint_names,
            'all_primitives_have_joint_weights': all('JOINTS_0' in p['attributes'] and 'WEIGHTS_0' in p['attributes'] for p in primitives),
            'mesh_nodes_with_skin': sum('skin' in n for n in gltf['nodes']),
            'materials': len(gltf.get('materials', [])), 'images': len(gltf.get('images', [])),
            'bytes': OUTPUT.stat().st_size,
            'source_images': len(source_gltf.get('images', [])),
        }
        assert {'torso', 'neck', 'head'}.issubset(joint_names)
        assert validation['all_primitives_have_joint_weights'] and validation['mesh_nodes_with_skin']
        assert validation['images'] == validation['source_images'], 'Texture count changed'
        validation['material_semantics_and_texture_payloads_identical'] = appearance_signature(SOURCE) == appearance_signature(OUTPUT)
        assert validation['material_semantics_and_texture_payloads_identical'], 'Material/texture changed'
        result.update(exported=True, export_path=str(OUTPUT), export_validation=validation)
    result['source_unchanged'] = original_hash == digest(SOURCE)
    RESULT.write_text(json.dumps(result, indent=2) + '\n')
    print('RIG_REPORT', RESULT, json.dumps(result['weights']))


if __name__ == '__main__':
    main()
