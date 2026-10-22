import { Component, Suspense, useEffect, useMemo, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { Canvas, useFrame, useLoader, useThree } from '@react-three/fiber'
import { Environment, Lightformer, useGLTF } from '@react-three/drei'
import { Box3, MathUtils, Matrix4, MeshStandardMaterial, OrthographicCamera, Quaternion, SkinnedMesh, TextureLoader, Vector3 } from 'three'
import { clone } from 'three/examples/jsm/utils/SkeletonUtils.js'
import { advanceAvatarMotion, createAvatarMotion } from './avatarMotion'
import { applyHeadPose, inspectHeadRig } from './avatarRig'
import { AVATAR_EYES } from './avatarEyeConfig'
import { patchEyeMaterial } from './eyeShader'
import { getVisualTuning, visualDiagnostics } from './visualTuning'

const MODEL_URL = '/models/my-avatar-eye-prototype-neutral.glb'
const EYE_TEXTURES = AVATAR_EYES.eyes.flatMap(eye => [eye.base, eye.mr, eye.mask, eye.normal])

interface TrackingInput {
  x: number
  y: number
  reducedMotion: boolean
  active: boolean
  lastMove: number
}

function useWindowTracking(): RefObject<TrackingInput> {
  const input = useRef<TrackingInput>({ x: 0, y: 0, reducedMotion: true, active: false, lastMove: 0 })
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    const reset = () => { input.current.x = 0; input.current.y = 0; input.current.active = false }
    const syncPreference = () => {
      input.current.reducedMotion = preference.matches
      reset()
    }
    const track = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || !finePointer.matches) { reset(); return }
      if (input.current.reducedMotion) return
      input.current.active = true
      input.current.lastMove = performance.now()
      input.current.x = MathUtils.clamp(event.clientX / window.innerWidth * 2 - 1, -1, 1)
      input.current.y = MathUtils.clamp(1 - event.clientY / window.innerHeight * 2, -1, 1)
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) reset() }
    const visibility = () => { if (document.hidden) reset() }
    syncPreference()
    preference.addEventListener('change', syncPreference)
    finePointer.addEventListener('change', reset)
    window.addEventListener('pointermove', track, { passive: true })
    window.addEventListener('pointerout', leave)
    window.addEventListener('blur', reset)
    window.addEventListener('resize', reset)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      preference.removeEventListener('change', syncPreference)
      finePointer.removeEventListener('change', reset)
      window.removeEventListener('pointermove', track)
      window.removeEventListener('pointerout', leave)
      window.removeEventListener('blur', reset)
      window.removeEventListener('resize', reset)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [])
  return input
}

function ResponsiveCamera() {
  const { camera, size } = useThree()
  useEffect(() => {
    if (camera instanceof OrthographicCamera) {
      // Rigged model is normalized to 2.6 units high, with room for head turns.
      camera.zoom = Math.min(size.width / 2.6, size.height / 3.2, 170)
      camera.updateProjectionMatrix()
    }
  }, [camera, size.width, size.height])
  return null
}

function RiggedAvatar({ input }: { input: RefObject<TrackingInput> }) {
  const { scene } = useGLTF(MODEL_URL)
  const textures = useLoader(TextureLoader, EYE_TEXTURES)
  const avatar = useMemo(() => {
    // Skeleton-aware clone isolates bone transforms from Drei's cached asset.
    // Geometry and textures stay shared; only this clone's material gets the eye shader.
    const model = clone(scene)
    model.updateMatrixWorld(true)
    const binding = inspectHeadRig(model)
    let mesh: SkinnedMesh | undefined
    model.traverse(object => { if (object instanceof SkinnedMesh) mesh = object })
    if (!mesh || !(mesh.material instanceof MeshStandardMaterial)) throw new Error('Expected the prototype skinned PBR mesh.')
    const headIndex = mesh.skeleton.bones.indexOf(binding.head)
    if (headIndex < 0) throw new Error('Head joint missing from skin.')
    const material = mesh.material.clone()
    mesh.material = material
    const uniforms = patchEyeMaterial(material, AVATAR_EYES, textures)
    const bounds = new Box3().setFromObject(model)
    const center = bounds.getCenter(new Vector3())
    const scale = 2.6 / bounds.getSize(new Vector3()).y
    return {
      model, binding, scale, material, uniforms,
      inverseHead: mesh.skeleton.boneInverses[headIndex],
      offset: center.multiplyScalar(-scale),
    }
  }, [scene, textures])
  const motion = useRef(createAvatarMotion())
  const rotation = useMemo(() => new Quaternion(), [])
  const normalTransform = useMemo(() => new Matrix4(), [])
  useEffect(() => () => { avatar.material.dispose() }, [avatar])

  useFrame(({ camera }, delta) => {
    const tuning = getVisualTuning()
    const { x, y, reducedMotion, active, lastMove } = input.current
    if (reducedMotion || tuning.freezeHead) {
      motion.current = createAvatarMotion()
      avatar.binding.head.quaternion.copy(avatar.binding.rest)
    } else {
      advanceAvatarMotion(motion.current, x, y, active, delta)
      applyHeadPose(avatar.binding, motion.current.pose, rotation)
    }
    // Include the responsive parent scale/offset and current head skin transform.
    // Projection coordinates remain in bind space; shading normals follow the head.
    avatar.model.updateWorldMatrix(true, true)
    normalTransform.multiplyMatrices(avatar.binding.head.matrixWorld, avatar.inverseHead)
      .premultiply(camera.matrixWorldInverse)
    avatar.uniforms.eyeNormalToView.value.getNormalMatrix(normalTransform)
    const blend = reducedMotion ? 1 : 1 - Math.exp(-tuning.eyeResponse * Math.min(delta, 0.1))
    // Reach the tested safe gaze range earlier in a sweep, before the head catches up.
    // No extra displacement: smooth gain saturates at the original +/-1 uniforms.
    const gain = (value: number) => Math.tanh(value * 3) / Math.tanh(3)
    const preset = import.meta.env.DEV ? tuning.gazePreset : 'pointer'
    const manual = preset !== 'pointer'
    const eyesActive = tuning.eyesEnabled && !reducedMotion && (manual || (active && performance.now() - lastMove < 6000))
    const targetX = manual ? (preset === 'left' ? -1 : preset === 'right' ? 1 : 0) : gain(x)
    const targetY = manual ? (preset === 'up' ? 1 : preset === 'down' ? -1 : 0) : gain(y)
    for (const gaze of [avatar.uniforms.eyeGaze0.value, avatar.uniforms.eyeGaze1.value]) {
      gaze.x = MathUtils.lerp(gaze.x, eyesActive ? targetX * tuning.eyeStrength : 0, blend)
      gaze.y = MathUtils.lerp(gaze.y, eyesActive ? targetY * tuning.eyeStrength : 0, blend)
      if (!eyesActive && gaze.lengthSq() < 1e-8) gaze.set(0, 0)
    }
    if (import.meta.env.DEV) {
      visualDiagnostics.gazeX = avatar.uniforms.eyeGaze0.value.x
      visualDiagnostics.gazeY = avatar.uniforms.eyeGaze0.value.y
    }
    // Neck, torso, root transform, and all other bones are never animated.
  })

  return (
    <group position={avatar.offset} scale={avatar.scale} dispose={null}>
      <primitive object={avatar.model} />
    </group>
  )
}

class AvatarErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    return this.state.failed
      ? <div className="avatar-fallback" role="status">The avatar could not load. Please refresh or check that WebGL is enabled.</div>
      : this.props.children
  }
}

export default function InteractiveAvatar() {
  const input = useWindowTracking()
  return (
    <section className="avatar-stage" aria-label="3D avatar whose head and eyes follow your pointer">
      <AvatarErrorBoundary>
        <Canvas
          orthographic
          camera={{ position: [0, 0, 6], zoom: 130, near: 0.1, far: 30 }}
          dpr={[1, 1.5]}
          fallback={<div className="avatar-fallback">Your browser does not support the 3D avatar.</div>}
        >
          <ResponsiveCamera />
          <ambientLight intensity={0.8} />
          <hemisphereLight args={['#fff7f0', '#c5b8da', 0.8]} />
          <directionalLight position={[-3, 4, 5]} intensity={1.5} color="#fff5ed" />
          {/* Local low-resolution studio reflections preserve the source PBR
              materials without fetching an HDR or replacing their textures. */}
          <Environment resolution={64} frames={1}>
            <color attach="background" args={['#b9b3c2']} />
            <Lightformer position={[-3, 3, 4]} scale={[4, 4, 1]} intensity={1.5} target={[0, 0, 0]} />
            <Lightformer position={[3, 1, 3]} scale={[3, 4, 1]} intensity={0.8} target={[0, 0, 0]} />
          </Environment>
          <Suspense fallback={null}>
            <RiggedAvatar input={input} />
          </Suspense>
        </Canvas>
      </AvatarErrorBoundary>
      <p className="avatar-caption">A little space for me.<span>Move your pointer — I’m following along.</span></p>
    </section>
  )
}
