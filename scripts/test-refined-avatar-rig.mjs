// CPU skinning checks on the actual GLB using the same rest-pose binding as R3F.
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { Bone, Group, Object3D, Matrix4, Quaternion, Vector3 } from 'three'
import { inspectHeadRig, applyHeadPose } from '../src/components/avatarRig.ts'

const bytes = fs.readFileSync('public/models/my-avatar-head-refined.glb')
const length = bytes.readUInt32LE(12)
const gltf = JSON.parse(bytes.subarray(20, 20 + length).toString())
const binaryStart = 28 + length
const skin = gltf.skins[0]
assert.equal(gltf.skins.length, 1)
const nodes = gltf.nodes.map((node, index) => {
  const object = skin.joints.includes(index) ? new Bone() : new Object3D()
  object.name = node.name
  object.position.fromArray(node.translation ?? [0, 0, 0])
  object.quaternion.fromArray(node.rotation ?? [0, 0, 0, 1])
  object.scale.fromArray(node.scale ?? [1, 1, 1])
  return object
})
gltf.nodes.forEach((node, index) => (node.children ?? []).forEach(child => nodes[index].add(nodes[child])))
const model = new Group()
gltf.scenes[gltf.scene ?? 0].nodes.forEach(index => model.add(nodes[index]))
const binding = inspectHeadRig(model)
assert(Math.abs(binding.rest.w - 1) > 1e-5, 'Refined local rest rotation must be retained')
const restTransforms = nodes.map(node => ({ position: node.position.clone(), quaternion: node.quaternion.clone(), scale: node.scale.clone() }))

function accessor(id) {
  const a = gltf.accessors[id], view = gltf.bufferViews[a.bufferView]
  const width = { SCALAR: 1, VEC3: 3, VEC4: 4, MAT4: 16 }[a.type]
  const size = { 5126: 4, 5123: 2, 5121: 1 }[a.componentType]
  assert(width && size)
  const offset = binaryStart + (view.byteOffset ?? 0) + (a.byteOffset ?? 0)
  return { count: a.count, read(index, channel) {
    const at = offset + index * (view.byteStride ?? width * size) + channel * size
    return a.componentType === 5126 ? bytes.readFloatLE(at) : a.componentType === 5123 ? bytes.readUInt16LE(at) : bytes.readUInt8(at)
  } }
}
const inverseData = accessor(skin.inverseBindMatrices)
const inverses = skin.joints.map((_, index) => new Matrix4().fromArray(Array.from({ length: 16 }, (_, channel) => inverseData.read(index, channel))))
const primitive = gltf.meshes[0].primitives[0]
const positions = accessor(primitive.attributes.POSITION)
const joints = accessor(primitive.attributes.JOINTS_0)
const weights = accessor(primitive.attributes.WEIGHTS_0)
const headIndex = skin.joints.indexOf(nodes.indexOf(binding.head))
const motion = JSON.parse(fs.readFileSync('reports/refined-avatar-motion-tests.json'))
const radians = Math.PI / 180
const poses = [
  { name: 'neutral', yaw: 0, pitch: 0, roll: 0 },
  { name: 'isolated_right35', yaw: 35 * radians, pitch: 0, roll: 0 },
  { name: 'isolated_left35', yaw: -35 * radians, pitch: 0, roll: 0 },
  { name: 'isolated_up15', yaw: 0, pitch: -15 * radians, roll: 0 },
  { name: 'isolated_down15', yaw: 0, pitch: 15 * radians, roll: 0 },
  ...motion.selectedPoses,
]
const scratch = new Quaternion(), original = new Vector3(), result = new Vector3(), transformed = new Vector3()
const checks = []
for (const pose of poses) {
  applyHeadPose(binding, pose, scratch)
  model.updateMatrixWorld(true)
  const matrices = skin.joints.map((index, joint) => new Matrix4().multiplyMatrices(nodes[index].matrixWorld, inverses[joint]))
  const forward = new Vector3(0, 0, 1).applyQuaternion(binding.head.getWorldQuaternion(new Quaternion()))
  if (pose.name === 'isolated_right35') assert(forward.x > 0.5)
  if (pose.name === 'isolated_left35') assert(forward.x < -0.5)
  if (pose.name === 'isolated_up15') assert(forward.y > 0.25)
  if (pose.name === 'isolated_down15') assert(forward.y < -0.25)
  let fixed = 0, maxFixed = 0, maxMoved = 0, maxError = 0
  for (let i = 0; i < positions.count; i++) {
    original.set(positions.read(i, 0), positions.read(i, 1), positions.read(i, 2))
    result.set(0, 0, 0)
    let headWeight = 0, sum = 0
    for (let k = 0; k < 4; k++) {
      const weight = weights.read(i, k), joint = joints.read(i, k)
      sum += weight
      if (joint === headIndex) headWeight += weight
      if (weight) result.addScaledVector(transformed.copy(original).applyMatrix4(matrices[joint]), weight)
    }
    assert(Math.abs(sum - 1) < 1e-5)
    const error = original.distanceTo(result)
    maxError = Math.max(maxError, error)
    if (!headWeight) { fixed++; maxFixed = Math.max(maxFixed, error) }
    else maxMoved = Math.max(maxMoved, error)
  }
  assert(maxFixed < 1e-5)
  if (pose.name === 'neutral') {
    assert(binding.head.quaternion.equals(binding.rest))
    assert(maxError < 1e-5)
  } else assert(maxMoved > 0)
  nodes.forEach((node, index) => {
    assert(node.position.equals(restTransforms[index].position))
    assert(node.scale.equals(restTransforms[index].scale))
    if (node !== binding.head) assert(node.quaternion.equals(restTransforms[index].quaternion))
  })
  checks.push({ name: pose.name, fixedVertices: fixed, maxFixedDisplacement: maxFixed, maxHeadDisplacement: maxMoved })
}
const report = { hierarchy: 'AvatarHeadPrototype → torso → neck → head', localHeadRestQuaternion: binding.rest.toArray(), verticesCheckedPerPose: positions.count, checks }
fs.writeFileSync('reports/refined-avatar-rig-tests.json', JSON.stringify(report, null, 2) + '\n')
console.log(JSON.stringify({ posesChecked: checks.length, verticesPerPose: positions.count, maxFixedDisplacement: Math.max(...checks.map(check => check.maxFixedDisplacement)), directionAndRestTransformChecks: 'passed' }, null, 2))
