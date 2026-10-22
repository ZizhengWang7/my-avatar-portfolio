import { Component, Suspense, useEffect, useMemo, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Environment, Html, Lightformer, useGLTF } from '@react-three/drei'
import { Box3, MathUtils, OrthographicCamera, Quaternion, Vector3 } from 'three'
import { clone } from 'three/examples/jsm/utils/SkeletonUtils.js'
import { advanceAvatarMotion, createAvatarMotion } from './avatarMotion'
import { applyHeadPose, inspectHeadRig } from './avatarRig'

const MODEL_URL = '/models/my-avatar-head-refined.glb'

interface TrackingInput {
  x: number
  y: number
  reducedMotion: boolean
  active: boolean
}

function useWindowTracking(): RefObject<TrackingInput> {
  const input = useRef<TrackingInput>({ x: 0, y: 0, reducedMotion: true, active: false })
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const reset = () => { input.current.x = 0; input.current.y = 0; input.current.active = false }
    const syncPreference = () => {
      input.current.reducedMotion = preference.matches
      reset()
    }
    const track = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || input.current.reducedMotion) return
      input.current.active = true
      input.current.x = MathUtils.clamp(event.clientX / window.innerWidth * 2 - 1, -1, 1)
      input.current.y = MathUtils.clamp(1 - event.clientY / window.innerHeight * 2, -1, 1)
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) reset() }
    const visibility = () => { if (document.hidden) reset() }
    syncPreference()
    preference.addEventListener('change', syncPreference)
    window.addEventListener('pointermove', track, { passive: true })
    window.addEventListener('pointerout', leave)
    window.addEventListener('blur', reset)
    window.addEventListener('resize', reset)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      preference.removeEventListener('change', syncPreference)
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
  const avatar = useMemo(() => {
    // Skeleton-aware clone isolates bone transforms from Drei's cached asset.
    // Geometry, textures and materials remain shared and unchanged.
    const model = clone(scene)
    model.updateMatrixWorld(true)
    const binding = inspectHeadRig(model)
    const bounds = new Box3().setFromObject(model)
    const center = bounds.getCenter(new Vector3())
    const scale = 2.6 / bounds.getSize(new Vector3()).y
    return {
      model, binding, scale,
      offset: center.multiplyScalar(-scale),
    }
  }, [scene])
  const motion = useRef(createAvatarMotion())
  const rotation = useMemo(() => new Quaternion(), [])

  useFrame((_, delta) => {
    const { x, y, reducedMotion, active } = input.current
    if (reducedMotion) {
      motion.current = createAvatarMotion()
      avatar.binding.head.quaternion.copy(avatar.binding.rest)
      return
    }
    advanceAvatarMotion(motion.current, x, y, active, delta)
    applyHeadPose(avatar.binding, motion.current.pose, rotation)
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
    <section className="avatar-stage" aria-label="3D avatar whose head follows your pointer">
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
          <Suspense fallback={<Html center><span role="status">Loading avatar…</span></Html>}>
            <RiggedAvatar input={input} />
          </Suspense>
        </Canvas>
      </AvatarErrorBoundary>
      <p className="avatar-caption">A little space for me.<span>Move your pointer — I’m following along.</span></p>
    </section>
  )
}
