import type { ReactNode } from 'react'

import { cn } from '../../lib/cn'
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
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={thickness}
          strokeLinecap="round"
          stroke={accentStroke[accent]}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-700 ease-out"
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
