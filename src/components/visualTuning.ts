// Mutable controls are read by animation callbacks, never React state per frame.
export const VISUAL_DEFAULTS = {
  density: 70, brightness: 1, size: 4.5, lifespan: 1,
  trailWidth: 24, rippleIntensity: 0.8,
  eyeStrength: 1, eyeResponse: 24, freezeHead: false, eyesEnabled: true,
  gazePreset: 'pointer',
}
export const visualTuning = { ...VISUAL_DEFAULTS }
export const visualDiagnostics = { shaderCompiled: false, gazeX: 0, gazeY: 0, particles: 0 }
export function getVisualTuning() {
  return import.meta.env.DEV ? visualTuning : VISUAL_DEFAULTS
}
