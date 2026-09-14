import type { Transition, Variants } from 'motion/react'

/**
 * The motion vocabulary. Every animation in the app comes from here, for the
 * same reason every colour comes from index.css: eight workspaces built by
 * hand would each end up with their own idea of "fast" and "springy".
 *
 * Rules this encodes:
 *  - Motion is short. Anything over ~400ms is in the user's way on a dashboard
 *    they open daily.
 *  - Entrances move a small distance. Big translations read as decoration.
 *  - Interactive feedback is spring-based; state changes are eased. Springs feel
 *    physical under a cursor, but overshoot is wrong for a progress bar.
 *  - Nothing here is load-bearing. With reduced motion every variant collapses
 *    to a plain crossfade, and the UI must still make sense.
 */

/** Standard easing - slight ease-out, no overshoot. */
export const EASE = [0.22, 0.61, 0.36, 1] as const

export const duration = {
  instant: 0.12,
  fast: 0.18,
  base: 0.28,
  slow: 0.42,
} as const

export const spring = {
  /** Buttons, cards under a cursor. Tight, barely any overshoot. */
  snappy: { type: 'spring', stiffness: 420, damping: 32, mass: 0.7 },
  /** Larger surfaces - modals, panels. */
  soft: { type: 'spring', stiffness: 260, damping: 30 },
} satisfies Record<string, Transition>

/** Fade-and-rise, the default entrance for a card or a section. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: duration.base, ease: EASE } },
}

/** Same, but sideways - for list rows and timeline items. */
export const slideIn: Variants = {
  hidden: { opacity: 0, x: -10 },
  visible: { opacity: 1, x: 0, transition: { duration: duration.base, ease: EASE } },
}

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1, transition: spring.soft },
}

/**
 * Container for a group that should animate in sequence. Children inherit the
 * timing, so a grid of cards only needs `variants={stagger}` on the wrapper and
 * `variants={rise}` on each child.
 */
export function stagger(step = 0.05, delay = 0): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren: step, delayChildren: delay } },
  }
}

/** Route-level transition. Deliberately plainer than component motion. */
export const pageTransition: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: duration.base, ease: EASE } },
  exit: { opacity: 0, y: -6, transition: { duration: duration.fast, ease: EASE } },
}

/**
 * Reduced motion does not mean "no feedback" - it means no movement. Elements
 * still appear and disappear, they just do not travel. Spread this over any
 * variant to strip the transforms.
 */
export const reducedVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: duration.fast } },
  exit: { opacity: 0, transition: { duration: duration.instant } },
}
