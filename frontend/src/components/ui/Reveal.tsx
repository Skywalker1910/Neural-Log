import type { ReactNode } from 'react'
import { m, type Variants } from 'motion/react'

import { cn } from '../../lib/cn'
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
      // min-w-0 for the same reason Card carries it: a Reveal is almost always
      // the direct child of a grid or flex container, so it is the element that
      // inherits min-width:auto and refuses to shrink. Card's own min-w-0 does
      // nothing when this wrapper sits between it and the grid.
      className={cn('min-w-0', className)}
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
      className={cn('min-w-0', className)}
      variants={reduced ? reducedVariants : stagger(step, delay)}
      initial="hidden"
      animate="visible"
    >
      {children}
    </m.div>
  )
}
