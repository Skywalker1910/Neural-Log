import { Pause, Play, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Exercise } from '../../api/types'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { patternLabel } from '../../lib/movementPatterns'
import { ExerciseAnimation } from './ExerciseAnimation'

export function ExerciseDemonstration({ exercise }: { exercise: Exercise }) {
  const reduced = usePrefersReducedMotion()
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [speed, setSpeed] = useState(1)
  const position = useRef(0)
  useEffect(() => {
    if (!playing || reduced) return
    let frame = 0
    let previous = 0
    function tick(now: number) {
      if (previous) position.current = (position.current + Math.min(now - previous, 80) / (4000 / speed)) % 1
      previous = now
      setProgress(position.current)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, reduced, speed])
  if (!exercise.movement_pattern) return <p>Follow the written instructions below.</p>
  return <div data-no-turn className="rounded-lg border border-current/10 p-3">
    <div className="flex items-center justify-center gap-3">
      <ExerciseAnimation pattern={exercise.movement_pattern} name={exercise.name} equipment={exercise.equipment} progress={progress} size={150} />
      <div className="text-xs"><p className="font-semibold">{patternLabel(exercise.movement_pattern)}</p><p className="mt-2 opacity-60">{progress < .12 || progress > .88 ? 'Starting position' : progress < .5 ? 'First half of the rep' : 'Return with control'}</p><p className="mt-3 opacity-60">Movement guide.<br />Read the cues below.</p></div>
    </div>
    <div className="mt-2 flex items-center gap-3 text-xs">
      <button type="button" aria-label={playing && !reduced ? 'Pause demonstration' : 'Play demonstration'} disabled={reduced} onClick={() => setPlaying(!playing)} className="rounded border border-current/20 p-2 disabled:opacity-30">{playing && !reduced ? <Pause size={14} /> : <Play size={14} />}</button>
      <input type="range" min="0" max="100" aria-label="Exercise movement position" value={Math.round(progress * 100)} onChange={(event) => { setPlaying(false); position.current = Number(event.target.value) / 100; setProgress(position.current) }} className="min-w-0 flex-1 accent-fitness" />
      <button type="button" aria-label="Reset demonstration" onClick={() => { position.current = 0; setProgress(0); setPlaying(false) }}><RotateCcw size={14} /></button>
      <select aria-label="Demonstration speed" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} className="bg-transparent"><option value={.5}>0.5×</option><option value={1}>1×</option></select>
    </div>
    {reduced && <p className="mt-2 text-xs opacity-60">Use the slider to inspect each position.</p>}
  </div>
}
