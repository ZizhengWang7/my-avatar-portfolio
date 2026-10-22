import { Bone, Quaternion, Vector3 } from 'three'
import type { Object3D } from 'three'
import type { HeadPose } from './avatarMotion'

export function inspectHeadRig(model: Object3D) {
  model.updateMatrixWorld(true)
  const head = model.getObjectByName('head')
  if (!(head instanceof Bone) || !(head.parent instanceof Bone) ||
    head.parent.name !== 'neck' || !(head.parent.parent instanceof Bone) ||
    head.parent.parent.name !== 'torso' || head.parent.parent.parent?.name !== 'AvatarHeadPrototype') {
    throw new Error('Expected AvatarHeadPrototype → torso → neck → head bones.')
  }
  const rest = head.quaternion.clone()
  // The refined joints have nonidentity local rest rotations. Convert model
  // world tracking axes into the head's rest frame instead of discarding them.
  const inverseWorldRest = head.getWorldQuaternion(new Quaternion()).invert()
  return {
    head, rest,
    yawAxis: new Vector3(0, 1, 0).applyQuaternion(inverseWorldRest),
    pitchAxis: new Vector3(1, 0, 0).applyQuaternion(inverseWorldRest),
    rollAxis: new Vector3(0, 0, 1).applyQuaternion(inverseWorldRest),
  }
}

export function applyHeadPose(binding: ReturnType<typeof inspectHeadRig>, pose: HeadPose, scratch: Quaternion) {
  binding.head.quaternion.copy(binding.rest)
    .multiply(scratch.setFromAxisAngle(binding.yawAxis, pose.yaw))
    .multiply(scratch.setFromAxisAngle(binding.pitchAxis, pose.pitch))
    .multiply(scratch.setFromAxisAngle(binding.rollAxis, pose.roll))
}
