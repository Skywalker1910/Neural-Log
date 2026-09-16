import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, m } from 'motion/react'
import { Sparkles, X } from 'lucide-react'

import { useGamificationSummary } from '../../api/queries'
import { Button } from '../ui/Button'
import { spring } from '../../lib/motion'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'

/**
 * Notices when your level goes up, wherever you are.
 *
 * Derived from the gamification summary rather than from a save response, for a
 * reason that matters: a level-up is caused by XP, and since R7 every workspace
 * awards XP. Wiring this into the checklist's response - the only place that
 * reports `newly_earned_badges` - would celebrate a level earned by ticking
 * boxes and stay silent for one earned by a two-hour training session.
 *
 * So it lives in the shell and watches the number. Any mutation that invalidates
 * the summary will surface it.
 */
const DISMISS_AFTER_MS = 6000

export function LevelUpCelebration() {
  const summary = useGamificationSummary()
  const reduced = usePrefersReducedMotion()
  const [reached, setReached] = useState<number | null>(null)

  /*
    The previously *seen* level, not the previous render's. It starts undefined
    and is filled on the first successful load, which is what stops the app
    congratulating you on being level 6 every time you open it - the first
    observation is a starting point, not an increase.
  */
  const seen = useRef<number | null>(null)
  const level = summary.data?.level ?? null

  useEffect(() => {
    if (level === null) return
    const previous = seen.current
    seen.current = level
    if (previous !== null && level > previous) setReached(level)
  }, [level])

  useEffect(() => {
    if (reached === null) return
    const timer = window.setTimeout(() => setReached(null), DISMISS_AFTER_MS)
    return () => window.clearTimeout(timer)
  }, [reached])

  return (
    <AnimatePresence>
      {reached !== null && (
        <m.div
          role="status"
          aria-live="polite"
          className="fixed inset-x-4 bottom-24 z-50 mx-auto max-w-md lg:bottom-8"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 24, scale: 0.96 }}
          animate={reduced ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, y: 16, scale: 0.98 }}
          transition={spring.soft}
        >
          <div className="material-panel flex items-start gap-3 rounded-lg border border-discipline/40 p-4 shadow-overlay">
            <m.span
              className="flex size-10 shrink-0 items-center justify-center rounded-pill bg-discipline/15 text-discipline"
              /* The one flourish. Under reduced motion it simply appears -
                 the content is never gated behind an animation that may not run. */
              initial={reduced ? false : { rotate: -20, scale: 0.6 }}
              animate={reduced ? false : { rotate: 0, scale: 1 }}
              transition={spring.snappy}
            >
              <Sparkles size={20} aria-hidden />
            </m.span>

            <div className="min-w-0 flex-1">
              <p className="text-label font-semibold text-ink">Level {reached}</p>
              <p className="text-meta text-ink-muted">
                Earned from what you logged — every workspace pays into it.
              </p>
            </div>

            <Button
              size="sm"
              variant="ghost"
              icon={X}
              aria-label="Dismiss"
              onClick={() => setReached(null)}
            />
          </div>
        </m.div>
      )}
    </AnimatePresence>
  )
}
