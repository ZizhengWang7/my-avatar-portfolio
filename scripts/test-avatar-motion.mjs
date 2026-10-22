// Node 22: node --experimental-strip-types scripts/test-avatar-motion.mjs
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { AVATAR_MOTION, advanceAvatarMotion, createAvatarMotion, stepSpring, constrainHeadPose } from '../src/components/avatarMotion.ts'

for (const damping of [18.5, 21, 2 * Math.sqrt(150), 30]) {
  const results = [30, 60, 144].map(fps => {
    const axis = { position: 0, velocity: 0 }
    for (let i = 0; i < fps; i++) stepSpring(axis, 1, 150, damping, 1 / fps)
    return axis
  })
  for (const result of results) {
    assert(Math.abs(result.position - results[0].position) < 1e-10)
    assert(Math.abs(result.velocity - results[0].velocity) < 1e-10)
  }
}

const overshoot = damping => {
  const axis = { position: 0, velocity: 0 }
  let peak = 0
  for (let i = 0; i < 600; i++) {
    stepSpring(axis, 1, AVATAR_MOTION.springStiffness, damping, 1 / 240)
    peak = Math.max(peak, axis.position)
  }
  return peak - 1
}
const slow = overshoot(AVATAR_MOTION.springDamping)
const fast = overshoot(AVATAR_MOTION.fastSpringDamping)
assert(fast > slow && fast > 0 && fast < 0.05)

const limits = [AVATAR_MOTION.maxYawDegrees, AVATAR_MOTION.maxPitchDegrees, AVATAR_MOTION.maxRollDegrees].map(x => x * Math.PI / 180)
const degrees = 180 / Math.PI
const report = { frameRatesTested: [30, 60, 144], slowOvershootPercent: slow * 100, fastOvershootPercent: fast * 100, scenarios: [], selectedPoses: [] }

// Check continuity through the soft knee, plus aggressive poses beyond limits.
const knee = AVATAR_MOTION.envelopeKnee * limits[0]
const epsilon = 1e-6
const left = constrainHeadPose(knee - epsilon, 0, 0).yaw
const middle = constrainHeadPose(knee, 0, 0).yaw
const right = constrainHeadPose(knee + epsilon, 0, 0).yaw
assert(Math.abs((middle - left) / epsilon - (right - middle) / epsilon) < 1e-6)
for (const yaw of [-70, 0, 70]) for (const pitch of [-45, 0, 45]) for (const roll of [-10, 0, 10]) {
  const pose = constrainHeadPose(yaw / degrees, pitch / degrees, roll / degrees)
  const length = Math.hypot(pose.yaw / limits[0], pose.pitch / limits[1], pose.roll / limits[2])
  assert(length <= 1 + 1e-12)
}

const scenarios = {
  slow_circle: t => [Math.sin(t * 0.7), Math.cos(t * 0.7)],
  single_horizontal_flick: t => [t < 2 ? -1 : 1, 0],
  quick_horizontal_sweeps: t => [Math.sign(Math.sin(t * 10)), 0],
  quick_diagonal_sweeps: t => [Math.sign(Math.sin(t * 8)), Math.sign(Math.cos(t * 7))],
  corner_holds: t => [[-1, -1], [1, -1], [1, 1], [-1, 1]][Math.floor(t / 2) % 4],
  vertical_sweeps: t => [0, Math.sign(Math.sin(t * 9))],
  jitter: t => [0.001 * Math.sin(t * 110), 0.001 * Math.cos(t * 95)],
}
for (const fps of report.frameRatesTested) {
  for (const [name, pointer] of Object.entries(scenarios)) {
    const state = createAvatarMotion()
    const maxima = { yaw: 0, pitch: 0, roll: 0 }
    const peaks = {}
    let maxStep = 0
    let previous = { yaw: 0, pitch: 0, roll: 0 }
    for (let i = 0; i < fps * 12; i++) {
      const [x, y] = pointer(i / fps)
      advanceAvatarMotion(state, x, y, true, 1 / fps)
      const pose = state.pose
      const radius = Math.hypot(pose.yaw / limits[0], pose.pitch / limits[1], pose.roll / limits[2])
      assert(Number.isFinite(radius) && radius <= 1 + 1e-12)
      // Large yaw can occur only with reduced pitch/roll, below tested
      // conservative combined ±30 / ±10 / ±3 poses.
      if (Math.abs(pose.yaw) >= 30 / degrees) {
        assert(Math.abs(pose.pitch) < 10 / degrees)
        assert(Math.abs(pose.roll) < 3 / degrees)
      }
      for (const axis of ['yaw', 'pitch', 'roll']) {
        if (Math.abs(pose[axis]) * degrees > maxima[axis]) {
          maxima[axis] = Math.abs(pose[axis]) * degrees
          peaks[axis] = { ...pose }
        }
        maxStep = Math.max(maxStep, Math.abs(pose[axis] - previous[axis]) * degrees)
      }
      previous = { ...pose }
    }
    // A full instantaneous 60° pointer reversal must still be animated.
    assert(maxStep < 360 / fps, `${name} snapped at ${fps} Hz: ${maxStep}`)
    if (name === 'jitter') assert(maxima.yaw < 0.05 && maxima.pitch < 0.05)
    if (fps === 60 && name !== 'jitter') {
      for (const [axis, pose] of Object.entries(peaks)) report.selectedPoses.push({ name: `${name}_${axis}_peak`, ...pose })
    }
    advanceAvatarMotion(state, 0, 0, false, 5)
    for (let i = 0; i < fps * 4; i++) advanceAvatarMotion(state, 0, 0, false, 1 / fps)
    for (const axis of [state.yaw, state.pitch, state.roll]) assert(Math.abs(axis.position) < 1e-8 && Math.abs(axis.velocity) < 1e-8)
    for (const angle of Object.values(state.pose)) assert(Math.abs(angle) < 1e-8)
    report.scenarios.push({ name, fps, maximaDegrees: maxima, maximumFrameStepDegrees: maxStep })
  }
}
report.envelopeContinuityAndNeutralReturn = 'passed'
report.observedMaximaDegrees = Object.fromEntries(['yaw', 'pitch', 'roll'].map(axis => [axis, Math.max(...report.scenarios.map(s => s.maximaDegrees[axis]))]))
fs.mkdirSync('reports', { recursive: true })
fs.writeFileSync('reports/refined-avatar-motion-tests.json', JSON.stringify(report, null, 2) + '\n')
console.log(JSON.stringify({ frameRatesTested: report.frameRatesTested, observedMaximaDegrees: report.observedMaximaDegrees, scenariosPassed: report.scenarios.length, envelopeContinuityAndNeutralReturn: 'passed' }, null, 2))
