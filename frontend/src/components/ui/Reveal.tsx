import type { ReactNode } from 'react'
import { m, type Variants } from 'motion/react'

import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { reducedVariants, rise, stagger } from '../../lib/motion'

interface RevealProps {
  children: ReactNode
  /** Which entrance to use. Defaults to fade-and-rise. */
  variants?: Variants
  /** Seconds. Only for one-off elements - prefer RevealGroup for lists. */
  delay?: number
  className?: string
}

/**
 * Entrance animation for a single element.
 *
 * Under `prefers-reduced-motion` the element still appears, it just does not
 * travel - the content is never gated behind an animation that might not run.
 */
export function Reveal({ children, variants = rise, delay, className }: RevealProps) {
  const reduced = usePrefersReducedMotion()

  return (
    <m.div
      className={className}
      variants={reduced ? reducedVariants : variants}
      initial="hidden"
      animate="visible"
      transition={delay ? { delay } : undefined}
    >
      {children}
    </m.div>
  )
}

interface RevealGroupProps {
  children: ReactNode
  /** Seconds between each child. */
  step?: number
  delay?: number
  className?: string
}

/**
 * Staggers its children in. Pair with `<Reveal>` children - they pick up the
 * sequence automatically through variant inheritance, so a grid of cards needs
 * no per-item delays.
 */
export function RevealGroup({ children, step = 0.05, delay = 0, className }: RevealGroupProps) {
  const reduced = usePrefersReducedMotion()

  return (
    <m.div
      className={className}
      variants={reduced ? reducedVariants : stagger(step, delay)}
      initial="hidden"
      animate="visible"
    >
      {children}
    </m.div>
  )
}
