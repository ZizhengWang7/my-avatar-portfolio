import { useEffect, useState } from 'react'
import VisualTuningPanel from './VisualTuningPanel'

// This entire module, including its listener, is excluded from production by App.
export default function DevelopmentTuning() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const toggle = (event: KeyboardEvent) => {
      if (!event.shiftKey || event.ctrlKey || event.metaKey || event.altKey ||
        event.code !== 'KeyD' || event.repeat || event.isComposing) return
      const target = event.target
      if (target instanceof HTMLElement && target.closest('input, textarea, select, [contenteditable="true"]')) return
      event.preventDefault()
      setVisible(previous => !previous)
    }
    window.addEventListener('keydown', toggle)
    return () => window.removeEventListener('keydown', toggle)
  }, [])
  return visible ? <VisualTuningPanel /> : null
}
