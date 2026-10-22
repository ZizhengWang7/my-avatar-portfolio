import './VisualTuningPanel.css'
import { useEffect, useState } from 'react'
import { visualTuning, visualDiagnostics, VISUAL_DEFAULTS } from './visualTuning'

export default function VisualTuningPanel() {
  const [settings, setSettings] = useState({ ...visualTuning })
  const [diagnostics, setDiagnostics] = useState({ ...visualDiagnostics })
  useEffect(() => {
    const timer = window.setInterval(() => setDiagnostics({ ...visualDiagnostics }), 250)
    return () => clearInterval(timer)
  }, [])
  const update = (change: Partial<typeof visualTuning>) => {
    Object.assign(visualTuning, change)
    setSettings({ ...visualTuning })
  }
  const sliders = [
    ['density', 'Particle density / sec', 15, 120, 1],
    ['brightness', 'Particle brightness', 0.2, 1, 0.05],
    ['size', 'Star size / px', 2, 7, 0.1],
    ['lifespan', 'Lifespan / sec', 0.4, 1.5, 0.1],
    ['trailWidth', 'Trail width / px', 10, 48, 1],
    ['rippleIntensity', 'Ripple intensity', 0, 2, 0.05],
    ['eyeStrength', 'Eye strength (safe maximum = 1)', 0, 1, 0.05],
    ['eyeResponse', 'Eye response / sec (higher = faster)', 5, 40, 1],
  ] as const
  return <details className="visual-tuning" open>
    <summary>Visual tuning · development only</summary>
    {sliders.map(([key, label, min, max, step]) => <label key={key}>{label}: {settings[key].toFixed(2)}
      <input aria-label={label} type="range" min={min} max={max} step={step} value={settings[key]} onChange={event => update({ [key]: +event.target.value })} />
    </label>)}
    <label><input type="checkbox" checked={settings.freezeHead} onChange={e => update({ freezeHead: e.target.checked })} /> Freeze head at neutral</label>
    <label><input type="checkbox" checked={settings.eyesEnabled} onChange={e => update({ eyesEnabled: e.target.checked })} /> Enable eye tracking</label>
    <label>Gaze comparison<select aria-label="Gaze comparison" value={settings.gazePreset} onChange={e => update({ gazePreset: e.target.value })}>
      {['pointer', 'center', 'left', 'right', 'up', 'down'].map(value => <option key={value}>{value}</option>)}
    </select></label>
    <button onClick={() => update({ ...VISUAL_DEFAULTS })}>Reset defaults</button>
    <output>Shader: {diagnostics.shaderCompiled ? 'compiled' : 'loading'} · gaze {diagnostics.gazeX.toFixed(2)}, {diagnostics.gazeY.toFixed(2)} · stars {diagnostics.particles}</output>
  </details>
}
