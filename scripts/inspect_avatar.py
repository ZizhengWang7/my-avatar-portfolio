"""Read-only, low-memory GLB inspection. Run with Blender --background --python.

No mesh copies, modifiers, renders, rigging, exports, or .blend saves are made.
Region labels are geometric hypotheses, never automatic anatomical selections.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class Components:
    def __init__(self, count):
        self.parent = array('I', range(count))
        self.rank = bytearray(count)

    def find(self, vertex):
        parent = self.parent
        while parent[vertex] != vertex:
            parent[vertex] = parent[parent[vertex]]
            vertex = parent[vertex]
        return vertex

    def join(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1


def bounds_record():
    return {'min': [float('inf')] * 3, 'max': [float('-inf')] * 3}


def extend(bounds, coordinate):
    for axis in range(3):
        bounds['min'][axis] = min(bounds['min'][axis], coordinate[axis])
        bounds['max'][axis] = max(bounds['max'][axis], coordinate[axis])


def summarize(mesh, connectivity, world):
    parts = {}
    for vertex in mesh.vertices:
        root = connectivity.find(vertex.index)
        part = parts.setdefault(root, {
            'component_id': root, 'vertices': 0, 'faces': 0, 'triangles': 0,
            'boundary_edges': 0, 'nonmanifold_edges': 0,
            'world_bounds': bounds_record(),
        })
        part['vertices'] += 1
        extend(part['world_bounds'], world @ vertex.co)
    # Compact incidence array avoids a Python dictionary of all triangle edges.
    incidence = array('I', [0]) * len(mesh.edges)
    for polygon in mesh.polygons:
        part = parts[connectivity.find(polygon.vertices[0])]
        part['faces'] += 1
        part['triangles'] += max(0, len(polygon.vertices) - 2)
        for loop in range(polygon.loop_start, polygon.loop_start + polygon.loop_total):
            incidence[mesh.loops[loop].edge_index] += 1
    for edge in mesh.edges:
        part = parts[connectivity.find(edge.vertices[0])]
        users = incidence[edge.index]
        part['boundary_edges'] += int(users == 1)
        part['nonmanifold_edges'] += int(users != 2)
    return sorted(parts.values(), key=lambda part: part['vertices'], reverse=True)


def inspect_mesh(obj):
    mesh = obj.data
    world = obj.matrix_world
    bounds = bounds_record()
    connectivity = Components(len(mesh.vertices))
    for vertex in mesh.vertices:
        extend(bounds, world @ vertex.co)
    for edge in mesh.edges:
        connectivity.join(*edge.vertices)
    physical = summarize(mesh, connectivity, world)

    # Virtual connectivity only: round coincident coordinates to catch UV/normal
    # seams. Never merge actual mesh vertices. This is a diagnostic, not a weld.
    span = max(bounds['max'][i] - bounds['min'][i] for i in range(3))
    tolerance = max(span * 1e-7, 1e-9)
    coincident = {}
    joined = 0
    for vertex in mesh.vertices:
        key = tuple(round(value / tolerance) for value in vertex.co)
        previous = coincident.get(key)
        if previous is None:
            coincident[key] = vertex.index
        else:
            if connectivity.find(vertex.index) != connectivity.find(previous):
                joined += 1
            connectivity.join(vertex.index, previous)
    del coincident
    virtual = summarize(mesh, connectivity, world)

    height = bounds['max'][2] - bounds['min'][2]
    region_counts = {'upper_45_percent': 0, 'middle_15_percent': 0, 'lower_40_percent': 0}
    slices = [{'height_fraction': [i / 24, (i + 1) / 24],
               'vertices': 0, 'world_bounds': bounds_record()} for i in range(24)]
    for vertex in mesh.vertices:
        coordinate = world @ vertex.co
        z = (coordinate.z - bounds['min'][2]) / max(height, 1e-9)
        key = 'upper_45_percent' if z >= 0.55 else 'middle_15_percent' if z >= 0.4 else 'lower_40_percent'
        region_counts[key] += 1
        band = slices[min(23, max(0, int(z * 24)))]
        band['vertices'] += 1
        extend(band['world_bounds'], coordinate)
    for band in slices:
        if not band['vertices']:
            band['world_bounds'] = None
    for part in virtual:
        box = part['world_bounds']
        part['world_center'] = [(box['min'][i] + box['max'][i]) / 2 for i in range(3)]
        part['world_dimensions'] = [box['max'][i] - box['min'][i] for i in range(3)]
        part['height_fraction_center'] = (part['world_center'][2] - bounds['min'][2]) / max(height, 1e-9)
        # Broad filter intentionally includes false positives (stickers, teeth,
        # hair, etc.). Anatomy must be confirmed visually before separation.
        part['possible_upper_face_island'] = (
            part['height_fraction_center'] > 0.5
            and max(part['world_dimensions']) < span * 0.3
            and part['vertices'] >= 20
        )
    return {
        'object': obj.name, 'mesh': mesh.name,
        'vertices': len(mesh.vertices), 'edges': len(mesh.edges),
        'faces': len(mesh.polygons),
        'triangles': sum(max(0, len(p.vertices) - 2) for p in mesh.polygons),
        'world_bounds': bounds, 'world_matrix': [list(row) for row in world],
        'uv_layers': [layer.name for layer in mesh.uv_layers],
        'vertex_groups': [group.name for group in obj.vertex_groups],
        'shape_keys': [key.name for key in mesh.shape_keys.key_blocks] if mesh.shape_keys else [],
        'modifiers': [{'name': mod.name, 'type': mod.type} for mod in obj.modifiers],
        'physical_components': physical,
        'physical_component_count': len(physical),
        'virtual_coincident_components': virtual,
        'virtual_component_count': len(virtual),
        'virtual_join_count': joined,
        'virtual_rounding_cell_local_units': tolerance,
        'edge_count_caveat': 'Boundary/nonmanifold counts use original exported edges even in virtual component summaries; these are not counts on a welded mesh.',
        'region_vertex_counts': region_counts,
        'vertical_profile_24_bands': slices,
        'region_caveat': 'Z-up vertical bands only; not verified anatomical boundaries. No orientation or eye identity inferred from filenames.',
    }


def main():
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    parser.add_argument('--input', type=Path, default=root / 'public/assets/人物3d建模.glb')
    parser.add_argument('--output', type=Path, default=root / 'reports/avatar-inspection.json')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    source = args.input.resolve()
    original_hash = sha256(source)
    start = time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.threads_mode = 'FIXED'
    bpy.context.scene.render.threads = 2
    bpy.ops.import_scene.gltf(filepath=str(source))
    bpy.context.view_layer.update()
    meshes = [inspect_mesh(obj) for obj in bpy.context.scene.objects if obj.type == 'MESH']
    report = {
        'source': str(source), 'source_bytes': source.stat().st_size,
        'source_sha256_before': original_hash,
        'blender_version': bpy.app.version_string,
        'coordinate_system': 'Blender world coordinates, Z up; original glTF Y-up import transform applied.',
        'method': 'Union-find over mesh edges, then virtual rounded-coordinate adjacency. No bmesh, evaluated mesh, subdivision, render, or mesh duplication.',
        'objects': [{'name': obj.name, 'type': obj.type, 'parent': obj.parent.name if obj.parent else None} for obj in bpy.context.scene.objects],
        'meshes': meshes,
        'armatures': [{'name': obj.name, 'bones': [bone.name for bone in obj.data.bones]} for obj in bpy.context.scene.objects if obj.type == 'ARMATURE'],
        'actions': [action.name for action in bpy.data.actions],
        'materials': [{'name': mat.name, 'use_nodes': mat.use_nodes} for mat in bpy.data.materials],
        'images': [{'name': image.name, 'size': list(image.size), 'packed': image.packed_file is not None} for image in bpy.data.images],
        'assessment': {
            'safe_eye_separation': 'Not established. Small disconnected parts are candidates only; confirm complete eyeball surfaces, socket coverage, and UV/material continuity in Blender before separation.',
            'head_skinning_without_cutting': 'Technically possible with an armature and vertex weights, even on a single connected mesh. Suitability depends on neck topology and deformation tests; no automatic weights or rig created.',
            'blink_readiness': 'Requires verified eyelid geometry and authored blink deformation if no shape keys/rig are present.',
            'preserve_appearance': 'Retain the source as master. Preserve UVs, textures, material assignments, hair and sticker geometry; inspect deformation before considering retopology.',
        },
        'limitations': [
            'Connectivity cannot establish semantic identity, interior eye completeness, or deformation quality.',
            'Virtual coordinate rounding can miss near-coincident vertices and can join touching but distinct surfaces; no actual geometry is altered.',
            'No visual anatomy confirmation or animation/deformation test is performed in this inspection.',
        ],
    }
    report['source_sha256_after'] = sha256(source)
    single_surface = bool(meshes) and all(mesh['virtual_component_count'] == 1 for mesh in meshes)
    report['assessment']['observed_connectivity'] = (
        'Each mesh becomes one component under virtual coincident-coordinate adjacency. '
        'Loose-part separation cannot identify intact head/eyeball units; the physical fragments '
        'are consistent with seam-split geometry, not an anatomical rig.'
        if single_surface else
        'Multiple virtual components remain. Their anatomical identities need visual confirmation.'
    )
    if single_surface:
        report['assessment']['safe_eye_separation'] = (
            'Not safe to automate from connected components. No isolated whole-eyeball component '
            'was found under virtual adjacency. Inspect eye sockets in a working copy to determine '
            'whether eyes are fused surface geometry or can be selected manually; full rotating '
            'eyeballs and hidden socket coverage may need reconstruction.'
        )
    report['source_unchanged'] = original_hash == report['source_sha256_after']
    report['elapsed_seconds'] = round(time.monotonic() - start, 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('INSPECTION_REPORT', args.output.resolve())
    for mesh in meshes:
        print('MESH_SUMMARY', mesh['object'], mesh['vertices'], mesh['triangles'], 'components', mesh['physical_component_count'], 'virtual', mesh['virtual_component_count'])
    print('SOURCE_UNCHANGED', report['source_unchanged'])


if __name__ == '__main__':
    main()
