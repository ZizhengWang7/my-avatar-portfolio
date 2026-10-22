import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import { Group, MathUtils, OrthographicCamera } from 'three'

interface TrackingInput {
  x: number
  y: number
  reducedMotion: boolean
}

// Window input stays independent of the model: a future GLB rig can consume it too.
function useAvatarInput(): RefObject<TrackingInput> {
  const input = useRef<TrackingInput>({ x: 0, y: 0, reducedMotion: true })

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const syncPreference = () => {
      input.current.reducedMotion = preference.matches
      input.current.x = 0
      input.current.y = 0
    }
    const track = (event: PointerEvent) => {
      if (event.pointerType === 'touch' || input.current.reducedMotion) return
      input.current.x = MathUtils.clamp((event.clientX / window.innerWidth) * 2 - 1, -1, 1)
      input.current.y = MathUtils.clamp(1 - (event.clientY / window.innerHeight) * 2, -1, 1)
    }
    const reset = () => { input.current.x = 0; input.current.y = 0 }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) reset() }
    syncPreference()
    preference.addEventListener('change', syncPreference)
    window.addEventListener('pointermove', track, { passive: true })
    window.addEventListener('pointerout', leave)
    window.addEventListener('blur', reset)
    window.addEventListener('resize', reset)
    return () => {
      preference.removeEventListener('change', syncPreference)
      window.removeEventListener('pointermove', track)
      window.removeEventListener('pointerout', leave)
      window.removeEventListener('blur', reset)
      window.removeEventListener('resize', reset)
    }
  }, [])

  return input
}

interface SphereProps {
  position?: [number, number, number]
  scale: [number, number, number]
  color: string
}

function Shape({ position, scale, color }: SphereProps) {
  return (
    <mesh position={position} scale={scale}>
      <sphereGeometry args={[1, 40, 32]} />
      <meshToonMaterial color={color} />
    </mesh>
  )
}

function Eye({ x, input, blink }: {
  x: number
  input: RefObject<TrackingInput>
  blink: RefObject<number>
}) {
  const eye = useRef<Group>(null)
  const gaze = useRef<Group>(null)
  useFrame((_, delta) => {
    if (!eye.current || !gaze.current) return
    const { x: px, y: py, reducedMotion } = input.current
    // Small offsets keep the entire iris inside the white, even at extremes.
    gaze.current.position.x = MathUtils.damp(gaze.current.position.x, reducedMotion ? 0 : px * 0.048, 12, delta)
    gaze.current.position.y = MathUtils.damp(gaze.current.position.y, reducedMotion ? 0 : py * 0.035, 12, delta)
    const nx = gaze.current.position.x / 0.22
    const ny = gaze.current.position.y / 0.25
    gaze.current.position.z = 0.117 * Math.sqrt(1 - nx * nx - ny * ny)
    eye.current.scale.y = reducedMotion ? 1 : blink.current
  })
  return (
    <group position={[x, 0.12, 0.54]}>
      <group ref={eye}>
        <Shape scale={[0.22, 0.25, 0.12]} color="#fff9f3" />
        <group ref={gaze} position={[0, 0, 0.117]}>
          <Shape scale={[0.103, 0.119, 0.018]} color="#775387" />
          <Shape position={[0, 0, 0.017]} scale={[0.05, 0.068, 0.012]} color="#30283d" />
          <Shape position={[-0.026, 0.037, 0.028]} scale={[0.023, 0.026, 0.008]} color="#ffffff" />
        </group>
      </group>
    </group>
  )
}

// Fit the complete bust into narrow screens and short windows without cropping.
function ResponsiveCamera() {
  const { camera, size } = useThree()
  useEffect(() => {
    if (camera instanceof OrthographicCamera) {
      camera.zoom = Math.min(size.width / 3.1, size.height / 3.8, 130)
      camera.updateProjectionMatrix()
    }
  }, [camera, size.width, size.height])
  return null
}

function ProceduralBust({ input }: { input: RefObject<TrackingInput> }) {
  const head = useRef<Group>(null)
  const blink = useRef(1)
  const blinkClock = useRef({ next: 2.8, start: -1 })

  useFrame(({ clock }, delta) => {
    const { x, y, reducedMotion } = input.current
    if (head.current) {
      // Euler pitch is inverted so looking toward the top lifts the face.
      head.current.rotation.y = MathUtils.damp(head.current.rotation.y, reducedMotion ? 0 : x * MathUtils.degToRad(20), 5, delta)
      head.current.rotation.x = MathUtils.damp(head.current.rotation.x, reducedMotion ? 0 : -y * MathUtils.degToRad(12), 5, delta)
    }
    const now = clock.elapsedTime
    const timing = blinkClock.current
    if (reducedMotion) {
      blink.current = 1
      timing.start = -1
      timing.next = now + 3
      return
    }
    if (now >= timing.next && timing.start < 0) timing.start = now
    if (timing.start >= 0) {
      const progress = (now - timing.start) / 0.18
      blink.current = 1 - 0.97 * Math.sin(Math.min(progress, 1) * Math.PI)
      if (progress >= 1) {
        blink.current = 1
        timing.start = -1
        timing.next = now + 2.5 + Math.random() * 3.5
      }
    }
  })

  return (
    <group position={[0, -0.15, 0]}>
      {/* The torso and neck do not inherit head motion. */}
      <Shape position={[0, -0.94, -0.05]} scale={[1.12, 0.59, 0.48]} color="#8e79ba" />
      <mesh position={[0, -0.47, 0]}>
        <cylinderGeometry args={[0.22, 0.28, 0.62, 40]} />
        <meshToonMaterial color="#efbda7" />
      </mesh>
      <group ref={head} position={[0, 0.3, 0]} rotation={[0, 0, 0]}>
        <Shape scale={[0.73, 0.86, 0.6]} color="#f5cbb5" />
        <Shape position={[-0.72, -0.02, 0]} scale={[0.135, 0.22, 0.14]} color="#efbda7" />
        <Shape position={[0.72, -0.02, 0]} scale={[0.135, 0.22, 0.14]} color="#efbda7" />
        <Shape position={[0, 0.52, -0.11]} scale={[0.75, 0.48, 0.58]} color="#49384f" />
        <Shape position={[-0.33, 0.65, 0.32]} scale={[0.42, 0.24, 0.27]} color="#49384f" />
        <Shape position={[0.2, 0.69, 0.29]} scale={[0.36, 0.23, 0.26]} color="#49384f" />
        <Eye x={-0.275} input={input} blink={blink} />
        <Eye x={0.275} input={input} blink={blink} />
        <Shape position={[0, -0.13, 0.59]} scale={[0.105, 0.13, 0.12]} color="#eab29c" />
        <Shape position={[-0.43, -0.2, 0.49]} scale={[0.12, 0.065, 0.018]} color="#e8a4a2" />
        <Shape position={[0.43, -0.2, 0.49]} scale={[0.12, 0.065, 0.018]} color="#e8a4a2" />
        <Line points={[[-0.16, -0.35, 0.551], [-0.08, -0.39, 0.56], [0, -0.4, 0.565], [0.08, -0.39, 0.56], [0.16, -0.35, 0.551]]} color="#955e69" lineWidth={2.5} />
        {[-1, 1].map((side) => (
          <Line key={side} points={[[side * 0.13, 0.43, 0.54], [side * 0.27, 0.46, 0.54], [side * 0.4, 0.42, 0.51]]} color="#49384f" lineWidth={4} />
        ))}
      </group>
    </group>
  )
}

export default function InteractiveAvatar() {
  const input = useAvatarInput()
  const [unavailable, setUnavailable] = useState(false)
  return (
    <section className="avatar-stage" aria-label="Interactive cartoon avatar that follows your pointer">
      {unavailable ? (
        <div className="avatar-fallback">The avatar needs WebGL to appear. Try a browser with hardware acceleration enabled.</div>
      ) : (
        <Canvas
          orthographic
          camera={{ position: [0, 0, 6], zoom: 105 }}
          dpr={[1, 2]}
          fallback={<div className="avatar-fallback">Your browser does not support the 3D avatar.</div>}
          onCreated={({ gl }) => {
            gl.setClearColor('#eee8f6', 0)
          }}
          onError={() => setUnavailable(true)}
        >
          <ResponsiveCamera />
          <ambientLight intensity={1.6} />
          <hemisphereLight args={['#fff4ed', '#b1a0cb', 1.4]} />
          <directionalLight position={[-3, 4, 5]} intensity={2.2} color="#fff2e5" />
          <ProceduralBust input={input} />
        </Canvas>
      )}
      <p className="avatar-caption">A little space for me.<span>Move your pointer — I’m following along.</span></p>
    </section>
  )
}
