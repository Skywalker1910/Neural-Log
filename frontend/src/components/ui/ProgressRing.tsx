import type { ReactNode } from 'react'
import { m } from 'motion/react'

import { cn } from '../../lib/cn'
import { EASE, duration } from '../../lib/motion'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { accentStroke, type Accent } from '../../navigation'

interface ProgressRingProps {
  /** 0-100. Values outside the range are clamped rather than drawn wrong. */
  value: number
  size?: number
  thickness?: number
  accent?: Accent
  label?: ReactNode
  className?: string
  /** Describes the ring for screen readers, e.g. "Discipline score". */
  ariaLabel?: string
}

export function ProgressRing({
  value,
  size = 96,
  thickness = 8,
  accent = 'brand',
  label,
  className,
  ariaLabel,
}: ProgressRingProps) {
  const pct = Math.max(0, Math.min(100, value))
  const radius = (size - thickness) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - pct / 100)
  const reduced = usePrefersReducedMotion()

  return (
    <div
      className={cn('relative inline-flex items-center justify-center', className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={ariaLabel ? `${ariaLabel}: ${Math.round(pct)}%` : `${Math.round(pct)}%`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          stroke="var(--color-line)"
        />
        <m.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          strokeLinecap="round"
          stroke={accentStroke[accent]}
          strokeDasharray={circumference}
          // Draws in from empty on mount, not just on later value changes - the
          // ring filling up is the point of the component.
          initial={{ strokeDashoffset: reduced ? offset : circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: reduced ? 0 : duration.slow * 2, ease: EASE }}
        />
      </svg>
      {label && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          {label}
        </div>
      )}
    </div>
  )
}
