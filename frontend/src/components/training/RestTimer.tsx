import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, m } from 'motion/react'
import { Pause, Play, RotateCcw, Timer, X } from 'lucide-react'

import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'
import { spring } from '../../lib/motion'

const PRESETS = [60, 90, 120, 180]

function mmss(totalSeconds: number): string {
  const clamped = Math.max(0, totalSeconds)
  const minutes = Math.floor(clamped / 60)
  const seconds = clamped % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

interface RestTimerProps {
  open: boolean
  onClose: () => void
  /** Seconds. Changing it while running restarts the countdown. */
  initialSeconds?: number
}

/**
 * Countdown between sets.
 *
 * Deliberately driven by a target timestamp rather than by decrementing a
 * counter on an interval: browsers throttle timers in background tabs, and on a
 * phone the screen locks mid-set. A decrementing counter would drift or freeze;
 * comparing against a stored end-time means the timer is correct the moment you
 * look at it again, however long the tab was asleep.
 */
export function RestTimer({ open, onClose, initialSeconds = 90 }: RestTimerProps) {
  const [duration, setDuration] = useState(initialSeconds)
  const [remaining, setRemaining] = useState(initialSeconds)
  const [running, setRunning] = useState(false)
  const endsAt = useRef<number | null>(null)

  const start = useCallback((seconds: number) => {
    setDuration(seconds)
    setRemaining(seconds)
    endsAt.current = Date.now() + seconds * 1000
    setRunning(true)
  }, [])

  useEffect(() => {
    if (!running) return

    const tick = () => {
      if (endsAt.current === null) return
      const left = Math.round((endsAt.current - Date.now()) / 1000)
      setRemaining(left)
      if (left <= 0) {
        setRunning(false)
        endsAt.current = null
      }
    }

    tick()
    const id = window.setInterval(tick, 250)
    return () => window.clearInterval(id)
  }, [running])

  const done = remaining <= 0
  const progress = duration > 0 ? Math.max(0, Math.min(1, remaining / duration)) : 0

  return (
    <AnimatePresence>
      {open && (
        <m.div
          className="fixed inset-x-4 bottom-24 z-40 mx-auto max-w-sm lg:bottom-8"
          initial={{ opacity: 0, y: 20, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 14, scale: 0.98 }}
          transition={spring.soft}
        >
          <div
            className={cn(
              'overflow-hidden rounded-lg border bg-surface-overlay shadow-overlay',
              done ? 'border-success/50' : 'border-line-strong',
            )}
          >
            {/* Draining bar - readable at a glance from across a gym. */}
            <div className="h-1 bg-surface-raised">
              <div
                className={cn('h-full transition-[width] duration-200 ease-linear',
                  done ? 'bg-success' : 'bg-fitness')}
                style={{ width: `${progress * 100}%` }}
              />
            </div>

            <div className="flex items-center gap-3 p-3">
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-full',
                  done ? 'bg-success/15 text-success' : 'bg-fitness/15 text-fitness',
                )}
              >
                <Timer size={18} aria-hidden />
              </span>

              <div className="min-w-0 flex-1">
                <p
                  className={cn('tabular text-section font-bold',
                    done ? 'text-success' : 'text-ink')}
                  aria-live="polite"
                >
                  {done ? 'Rest over' : mmss(remaining)}
                </p>
                <div className="mt-1 flex flex-wrap gap-1">
                  {PRESETS.map((seconds) => (
                    <button
                      key={seconds}
                      type="button"
                      onClick={() => start(seconds)}
                      className={cn(
                        'rounded px-1.5 py-0.5 text-caption transition-colors',
                        duration === seconds && running
                          ? 'bg-fitness/20 text-fitness'
                          : 'text-ink-subtle hover:text-ink',
                      )}
                    >
                      {seconds}s
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-1">
                {running ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={Pause}
                    aria-label="Pause rest timer"
                    onClick={() => {
                      setRunning(false)
                      endsAt.current = null
                    }}
                  />
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={done ? RotateCcw : Play}
                    aria-label={done ? 'Restart rest timer' : 'Start rest timer'}
                    onClick={() => start(done ? duration : remaining)}
                  />
                )}
                <Button size="sm" variant="ghost" icon={X} aria-label="Close rest timer"
                        onClick={onClose} />
              </div>
            </div>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
