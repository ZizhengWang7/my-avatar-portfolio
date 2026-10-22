import { useEffect, useRef } from 'react'
import { getVisualTuning, visualDiagnostics } from './visualTuning'

const MAX_PARTICLES = 160
const MAX_RIPPLES = 32
const MAX_CANVAS_PIXELS = 4_000_000
const RIPPLE_ARCS = Array.from({ length: 32 }, (_, arc) => {
  const angle = (arc + 0.5) * Math.PI / 16
  return { x: Math.cos(angle), y: Math.sin(angle) }
})
// Illinois Orange accents over a predominantly light-blue water trail.
const ORANGE = '255, 95, 5'
const BLUE = '145, 214, 255'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  bornAt: number
  radius: number
  color: string
}

interface Ripple {
  x: number; y: number; bornAt: number
  duration: number; startRadius: number; maxRadius: number
  stroke: number; opacity: number; easing: number; waves: number; color: string
}

interface CursorTrailProps {
  /** Keep the center of this element clear, e.g. an avatar's face. */
  protectedSelector?: string
}

export default function CursorTrail({ protectedSelector = '.avatar-stage canvas' }: CursorTrailProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d', { alpha: true })
    if (!canvas || !context) return

    // Unit-space resources retain the existing gradient stops and star geometry.
    // Scaling the context reuses them without allocating gradients per particle/frame.
    const halos = new Map<string, CanvasGradient>()
    for (const color of [ORANGE, BLUE, '255, 255, 255']) {
      const glow = context.createRadialGradient(0, 0, 0, 0, 0, 1.8)
      glow.addColorStop(0, `rgba(${color}, 0.18)`)
      glow.addColorStop(0.35, `rgba(${color}, 0.08)`)
      glow.addColorStop(1, `rgba(${color}, 0)`)
      halos.set(color, glow)
    }
    const star = new Path2D()
    for (let point = 0; point < 8; point++) {
      const angle = point * Math.PI / 4 - Math.PI / 2
      const length = point % 2 ? 0.34 : 1
      const x = Math.cos(angle) * length, y = Math.sin(angle) * length
      if (point === 0) star.moveTo(x, y); else star.lineTo(x, y)
    }
    star.closePath()

    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const finePointer = matchMedia('(hover: hover) and (pointer: fine)')
    const particles: Particle[] = []
    const particlePool: Particle[] = Array.from({ length: MAX_PARTICLES }, () => ({ x: 0, y: 0, vx: 0, vy: 0, bornAt: 0, radius: 1, color: ORANGE }))
    const ripples: Ripple[] = []
    const ripplePool: Ripple[] = Array.from({ length: MAX_RIPPLES }, () => ({ x: 0, y: 0, bornAt: 0, duration: 0.6, startRadius: 3, maxRadius: 35, stroke: 1, opacity: 0.5, easing: 1.5, waves: 1, color: BLUE }))
    let enabled = false
    let width = 0, height = 0, dpr = 1
    let frame = 0, previousTime = 0, rippleDistance = 0, particleDistance = 0
    let rippleSpacing = 12 + Math.random() * 6
    let previousPointer: { x: number; y: number } | null = null
    let protectedBounds: DOMRect | null = null

    const measureProtected = () => {
      protectedBounds = document.querySelector(protectedSelector)?.getBoundingClientRect() ?? null
    }
    // Protect the face, not the entire 3D canvas and its empty margins.
    const visibilityAt = (x: number, y: number) => {
      if (!protectedBounds) return 1
      const bounds = protectedBounds
      const rx = Math.max(bounds.width * 0.20, 1)
      const ry = Math.max(bounds.height * 0.23, 1)
      const distance = Math.hypot((x - bounds.left - bounds.width / 2) / rx,
        (y - bounds.top - bounds.height * 0.40) / ry)
      const fade = Math.max(0, Math.min(1, (distance - 1) / 0.25))
      return fade * fade * (3 - 2 * fade)
    }
    const clear = () => {
      cancelAnimationFrame(frame)
      frame = 0
      while (particles.length) particlePool.push(particles.pop()!)
      while (ripples.length) ripplePool.push(ripples.pop()!)
      if (import.meta.env.DEV) visualDiagnostics.particles = 0
      previousPointer = null
      rippleSpacing = 12 + Math.random() * 6
      rippleDistance = 0
      particleDistance = 0
      context.clearRect(0, 0, width, height)
    }
    // Match the avatar's density cap and bound total backing pixels on large displays.
    const effectiveDpr = () => Math.min(devicePixelRatio || 1, 1.5,
      Math.sqrt(MAX_CANVAS_PIXELS / Math.max(1, innerWidth * innerHeight)))
    const resize = () => {
      width = innerWidth
      height = innerHeight
      dpr = effectiveDpr()
      const backingWidth = enabled ? Math.max(1, Math.floor(width * dpr)) : 1
      const backingHeight = enabled ? Math.max(1, Math.floor(height * dpr)) : 1
      if (canvas.width !== backingWidth) canvas.width = backingWidth
      if (canvas.height !== backingHeight) canvas.height = backingHeight
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      measureProtected()
    }
    const draw = (timestamp: number) => {
      frame = 0
      const settings = getVisualTuning()
      const dt = Math.min((timestamp - previousTime) / 1000, 0.05)
      previousTime = timestamp
      context.clearRect(0, 0, width, height)
      // Vary size, speed and wave count; most unoccluded rings need just one stroke.
      for (let i = ripples.length - 1; i >= 0; i--) {
        const ripple = ripples[i]
        const life = (timestamp / 1000 - ripple.bornAt) / ripple.duration
        if (life >= 1) {
          ripplePool.push(ripple); ripples[i] = ripples[ripples.length - 1]; ripples.pop(); continue
        }
        for (let wave = 0; wave < ripple.waves; wave++) {
          const progress = Math.max(0, (life - wave * 0.13) / (1 - wave * 0.13))
          if (progress <= 0) continue
          const radius = ripple.startRadius + (ripple.maxRadius - ripple.startRadius) * (1 - (1 - progress) ** ripple.easing)
          const opacity = settings.rippleIntensity * ripple.opacity * Math.min(1, progress / 0.12) * (1 - progress) ** 1.3 * (wave ? 0.65 : 1)
          const color = wave ? BLUE : ripple.color
          context.lineWidth = ripple.stroke * (wave ? 0.8 : 1)
          const bounds = protectedBounds
          const overlapsFace = bounds &&
            Math.abs(ripple.x - bounds.left - bounds.width / 2) < bounds.width * 0.25 + radius &&
            Math.abs(ripple.y - bounds.top - bounds.height * 0.40) < bounds.height * 0.2875 + radius
          // A ring wholly inside the protected ellipse contributes no visible pixels.
          if (bounds) {
            const rx = Math.max(bounds.width * 0.20, 1)
            const ry = Math.max(bounds.height * 0.23, 1)
            const centerDistance = Math.hypot((ripple.x - bounds.left - bounds.width / 2) / rx,
              (ripple.y - bounds.top - bounds.height * 0.40) / ry)
            if (centerDistance + radius / Math.min(rx, ry) <= 1) continue
          }
          if (!overlapsFace) {
            context.strokeStyle = `rgba(${color}, ${opacity})`
            context.beginPath(); context.arc(ripple.x, ripple.y, radius, 0, Math.PI * 2); context.stroke()
            continue
          }
          for (let arc = 0; arc < 32; arc++) {
            const direction = RIPPLE_ARCS[arc]
            const alpha = opacity * visibilityAt(ripple.x + direction.x * radius, ripple.y + direction.y * radius)
            if (alpha < 0.003) continue
            context.strokeStyle = `rgba(${color}, ${alpha})`
            context.beginPath()
            context.arc(ripple.x, ripple.y, radius, arc * Math.PI / 16, (arc + 1) * Math.PI / 16 + 0.01)
            context.stroke()
          }
        }
      }
      for (let i = particles.length - 1; i >= 0; i--) {
        const particle = particles[i]
        // Wall-clock lifetime remains correct after a stalled frame.
        const life = (timestamp / 1000 - particle.bornAt) / settings.lifespan
        if (life >= 1) { particlePool.push(particle); particles[i] = particles[particles.length - 1]; particles.pop(); continue }
        particle.x += particle.vx * dt
        particle.y += particle.vy * dt
        // Hold a bright center for the first quarter, then fade smoothly to one second.
        const fade = Math.max(0, (life - 0.25) / 0.75)
        const alpha = settings.brightness * (1 - fade * fade * (3 - 2 * fade)) * visibilityAt(particle.x, particle.y)
        if (alpha <= 0) continue
        const radius = particle.radius * settings.size * (1 - life * 0.25)
        context.setTransform(dpr * radius, 0, 0, dpr * radius, particle.x * dpr, particle.y * dpr)
        context.globalAlpha = alpha
        context.fillStyle = halos.get(particle.color)!
        context.fillRect(-1.8, -1.8, 3.6, 3.6)
        context.fillStyle = `rgb(${particle.color})`
        context.fill(star)
      }
      context.globalAlpha = 1
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (import.meta.env.DEV) visualDiagnostics.particles = particles.length
      if (particles.length || ripples.length) frame = requestAnimationFrame(draw)
    }
    const move = (event: PointerEvent) => {
      if (!enabled || event.pointerType !== 'mouse' || document.hidden) return
      if (dpr !== effectiveDpr()) resize()
      const now = performance.now() / 1000
      const settings = getVisualTuning()
      if (!protectedBounds) measureProtected()
      const x = event.clientX, y = event.clientY
      const previous = previousPointer ?? { x, y }
      const dx = x - previous.x, dy = y - previous.y
      const distance = Math.hypot(dx, dy)
      if (distance < 0.5 && previousPointer) return
      const nx = distance > 0 ? -dy / distance : 0
      const ny = distance > 0 ? dx / distance : 1
      // Distance interpolation keeps the ribbon continuous between sparse/fast events.
      // Bound work on teleports; retain leftover distance for ordinary tiny movements.
      const spacing = Math.max(4, 560 / settings.density, distance / 64)
      let at = previousPointer ? Math.max(0, spacing - particleDistance) : 0
      for (; at <= distance; at += spacing) {
        const fraction = distance ? at / distance : 1
        const px = previous.x + dx * fraction, py = previous.y + dy * fraction
        // One probabilistic layer halves emission, including orange, with real gaps.
        if (Math.random() > 0.7) continue
        const scatter = Math.random() * 2 - 1
        const offset = scatter * settings.trailWidth
        const along = (Math.random() - 0.5) * spacing * 1.2
        const sx = px + nx * offset + ny * along, sy = py + ny * offset - nx * along
        if (visibilityAt(sx, sy) === 0) continue
        const particle = particlePool.pop() ?? particles.shift()!
        particle.x = sx; particle.y = sy
        particle.vx = nx * scatter * 7; particle.vy = ny * scatter * 7 - 7
        particle.bornAt = now
        particle.radius = 0.22 + Math.random() ** 1.8 * 1.05
        const palette = Math.random()
        particle.color = palette < 0.35 ? ORANGE : palette < 0.75 ? BLUE : '255, 255, 255'
        particles.push(particle)
      }
      particleDistance = Math.max(0, distance - (at - spacing))
      // Independently interpolate ripple centers by distance, not event endpoints/time.
      let rippleAt = Math.max(0, rippleSpacing - rippleDistance)
      let emitted = 0
      while (rippleAt <= distance && emitted < 48) {
        const fraction = distance ? rippleAt / distance : 1
        const offset = (Math.random() - 0.5) * settings.trailWidth * 0.18
        const rx = previous.x + dx * fraction + nx * offset
        const ry = previous.y + dy * fraction + ny * offset
        if (settings.rippleIntensity > 0 && visibilityAt(rx, ry) > 0.2) {
          const ripple = ripplePool.pop() ?? ripples.shift()!
          const size = Math.random()
          ripple.x = rx; ripple.y = ry; ripple.bornAt = now
          ripple.duration = 0.6 + Math.random() * 0.2
          // Broader starts overlap the 12–18px spacing immediately; each class
          // then expands at its own pace, with occasional broad outer waves.
          ripple.startRadius = size < 0.3 ? 4 + Math.random() * 4 : size < 0.85 ? 8 + Math.random() * 8 : 14 + Math.random() * 8
          ripple.maxRadius = size < 0.3 ? 18 + Math.random() * 12 : size < 0.85 ? 34 + Math.random() * 18 : 58 + Math.random() * 22
          ripple.stroke = 0.55 + Math.random() * 0.95
          ripple.opacity = 0.3 + Math.random() * 0.45
          ripple.easing = 1.4 + Math.random() * 1.4
          ripple.waves = Math.random() < 0.3 ? 2 : 1
          const tint = Math.random()
          ripple.color = tint < 0.85 ? BLUE : tint < 0.95 ? '255, 255, 255' : ORANGE
          ripples.push(ripple)
        }
        emitted++
        rippleSpacing = 12 + Math.random() * 6
        rippleAt += rippleSpacing
      }
      rippleDistance = emitted >= 48 ? 0 : Math.max(0, distance - (rippleAt - rippleSpacing))
      if (previousPointer) { previousPointer.x = x; previousPointer.y = y }
      else previousPointer = { x, y }
      if (!frame) {
        previousTime = now * 1000
        frame = requestAnimationFrame(draw)
      }
    }
    const syncPreference = () => {
      enabled = !reduced.matches && finePointer.matches
      clear()
      resize()
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) clear() }
    const visibility = () => { if (document.hidden) clear() }
    resize()
    syncPreference()
    reduced.addEventListener('change', syncPreference)
    finePointer.addEventListener('change', syncPreference)
    window.addEventListener('pointermove', move, { passive: true })
    window.addEventListener('pointerout', leave)
    window.addEventListener('blur', clear)
    window.addEventListener('resize', resize)
    window.addEventListener('scroll', measureProtected, { passive: true, capture: true })
    document.addEventListener('visibilitychange', visibility)
    return () => {
      clear()
      reduced.removeEventListener('change', syncPreference)
      finePointer.removeEventListener('change', syncPreference)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerout', leave)
      window.removeEventListener('blur', clear)
      window.removeEventListener('resize', resize)
      window.removeEventListener('scroll', measureProtected, true)
      document.removeEventListener('visibilitychange', visibility)
      // Release the backing store on unmount (including React StrictMode remounts).
      canvas.width = 1
      canvas.height = 1
      halos.clear()
    }
  }, [protectedSelector])

  return <canvas ref={canvasRef} className="cursor-trail" aria-hidden="true" />
}
