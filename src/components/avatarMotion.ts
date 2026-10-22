// Refined rig: isolated yaw validated through 35 degrees. Combined motion
// stays within a conservative smooth envelope; no stacked axis maxima.
export const AVATAR_MOTION = {
  targetYawDegrees: 30,
  maxYawDegrees: 35,
  maxPitchDegrees: 15,
  maxRollDegrees: 3,
  envelopeKnee: 0.9,
  springStiffness: 150,
  springDamping: 21,
  fastSpringDamping: 18.5,
  speedSmoothing: 10,
} as const

export interface HeadPose { yaw: number; pitch: number; roll: number }

export interface SpringAxis { position: number; velocity: number }
export interface AvatarMotionState {
  pose: HeadPose
  yaw: SpringAxis
  pitch: SpringAxis
  roll: SpringAxis
  previousX: number
  previousY: number
  speed: number
  horizontalSpeed: number
}

export function createAvatarMotion(): AvatarMotionState {
  return {
    pose: { yaw: 0, pitch: 0, roll: 0 },
    yaw: { position: 0, velocity: 0 }, pitch: { position: 0, velocity: 0 },
    roll: { position: 0, velocity: 0 }, previousX: 0, previousY: 0,
    speed: 0, horizontalSpeed: 0,
  }
}

// Exact unit-mass damped spring for a constant target over dt. Unlike Euler
// integration this stays stable and consistent across different frame rates.
export function stepSpring(axis: SpringAxis, target: number, stiffness: number, damping: number, dt: number) {
  if (dt <= 0) return
  const halfDamping = damping / 2
  const displacement = axis.position - target
  const velocity = axis.velocity
  const discriminant = stiffness - halfDamping * halfDamping
  const decay = Math.exp(-halfDamping * dt)
  if (discriminant > 1e-8) {
    const frequency = Math.sqrt(discriminant)
    const cosine = Math.cos(frequency * dt)
    const sine = Math.sin(frequency * dt)
    axis.position = target + decay * (displacement * cosine + (velocity + halfDamping * displacement) / frequency * sine)
    axis.velocity = decay * (velocity * cosine - (halfDamping * velocity + stiffness * displacement) / frequency * sine)
  } else if (discriminant < -1e-8) {
    const frequency = Math.sqrt(-discriminant)
    const r1 = -halfDamping + frequency
    const r2 = -halfDamping - frequency
    const c1 = (velocity - r2 * displacement) / (r1 - r2)
    const c2 = displacement - c1
    axis.position = target + c1 * Math.exp(r1 * dt) + c2 * Math.exp(r2 * dt)
    axis.velocity = c1 * r1 * Math.exp(r1 * dt) + c2 * r2 * Math.exp(r2 * dt)
  } else {
    const c = velocity + halfDamping * displacement
    axis.position = target + decay * (displacement + c * dt)
    axis.velocity = decay * (velocity - halfDamping * c * dt)
  }
}

const radians = Math.PI / 180
const limits = [AVATAR_MOTION.maxYawDegrees, AVATAR_MOTION.maxPitchDegrees, AVATAR_MOTION.maxRollDegrees].map(value => value * radians)

// Smooth radial saturation of the *rendered* pose, leaving the spring state
// untouched. Identity inside the knee, with matching first/second derivatives
// at the knee, and an asymptotic limit: no hard position/velocity projection.
export function constrainHeadPose(yaw: number, pitch: number, roll: number): HeadPose {
  const radius = Math.hypot(yaw / limits[0], pitch / limits[1], roll / limits[2])
  const knee = AVATAR_MOTION.envelopeKnee
  const safeRadius = radius <= knee ? radius : knee + (1 - knee) * Math.tanh((radius - knee) / (1 - knee))
  const scale = radius > 0 ? safeRadius / radius : 1
  return { yaw: yaw * scale, pitch: pitch * scale, roll: roll * scale }
}

export function advanceAvatarMotion(state: AvatarMotionState, x: number, y: number, active: boolean, dt: number) {
  if (!(dt > 0) || !Number.isFinite(dt)) return
  // Avoid a velocity burst when a background tab resumes. Keep the pose and
  // continue smoothly, rather than jumping to the target after a long pause.
  if (dt > 0.15) {
    state.previousX = x; state.previousY = y
    state.speed = 0; state.horizontalSpeed = 0
    state.yaw.velocity = 0; state.pitch.velocity = 0; state.roll.velocity = 0
    dt = 1 / 60
  }
  const vx = active ? (x - state.previousX) / dt : 0
  const vy = active ? (y - state.previousY) / dt : 0
  const blend = 1 - Math.exp(-AVATAR_MOTION.speedSmoothing * dt)
  state.speed += (Math.min(8, Math.hypot(vx, vy)) - state.speed) * blend
  state.horizontalSpeed += (Math.max(-8, Math.min(8, vx)) - state.horizontalSpeed) * blend
  state.previousX = x; state.previousY = y
  const expressiveness = active ? Math.min(1, state.speed / 3) : 0
  const damping = AVATAR_MOTION.springDamping + (AVATAR_MOTION.fastSpringDamping - AVATAR_MOTION.springDamping) * expressiveness
  // Quick sweeps add lean and a little spring overshoot. Sustained yaw aims
  // at 30 degrees; 35 degrees is only the isolated-yaw safety ceiling.
  const yawTarget = x * AVATAR_MOTION.targetYawDegrees * radians
  const pitchTarget = -y * AVATAR_MOTION.maxPitchDegrees * radians
  const rollTarget = active ? -(0.35 * x + 0.65 * Math.tanh(state.horizontalSpeed / 2)) * AVATAR_MOTION.maxRollDegrees * radians : 0
  stepSpring(state.yaw, yawTarget, AVATAR_MOTION.springStiffness, damping, dt)
  stepSpring(state.pitch, pitchTarget, AVATAR_MOTION.springStiffness, damping, dt)
  stepSpring(state.roll, rollTarget, AVATAR_MOTION.springStiffness, damping, dt)
  state.pose = constrainHeadPose(state.yaw.position, state.pitch.position, state.roll.position)
}
