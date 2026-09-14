import { useEffect } from 'react'
import { animate, m, useMotionValue, useTransform } from 'motion/react'

import { EASE, duration as durations } from '../../lib/motion'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'

interface AnimatedNumberProps {
  value: number
  /** Decimal places. Scores are integers; body weight is not. */
  decimals?: number
  /** Rendered before and after the number - "+", "%", " kg". */
  prefix?: string
  suffix?: string
  className?: string
}

/**
 * A number that counts up to its value.
 *
 * Worth the code because this app's whole point is watching numbers move. A
 * discipline score that animates from 71 to 74 communicates change; one that
 * simply repaints does not.
 *
 * Drives a MotionValue rather than React state, so the count does not re-render
 * the component 60 times a second - the text node updates directly.
 */
export function AnimatedNumber({
  value,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
}: AnimatedNumberProps) {
  const reduced = usePrefersReducedMotion()
  const raw = useMotionValue(reduced ? value : 0)
  const text = useTransform(raw, (latest) => `${prefix}${latest.toFixed(decimals)}${suffix}`)

  useEffect(() => {
    if (reduced) {
      raw.set(value)
      return
    }
    const controls = animate(raw, value, {
      duration: durations.slow,
      ease: EASE,
    })
    return () => controls.stop()
  }, [value, reduced, raw])

  // tabular-nums keeps the width stable while digits change, so surrounding
  // layout does not jitter during the count.
  return <m.span className={className}>{text}</m.span>
}
