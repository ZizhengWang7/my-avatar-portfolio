import InteractiveAvatar from './components/InteractiveAvatar'
import CursorTrail from './components/CursorTrail'
import { lazy, Suspense } from 'react'
import './App.css'

const DevelopmentTuning = import.meta.env.DEV ? lazy(() => import('./components/DevelopmentTuning')) : null

function App() {
  return (
    <main className="homepage">
      <InteractiveAvatar />
      <CursorTrail />
      {DevelopmentTuning && <Suspense fallback={null}><DevelopmentTuning /></Suspense>}
    </main>
  )
}

export default App
