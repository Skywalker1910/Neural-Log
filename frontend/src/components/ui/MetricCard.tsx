import type { ReactNode } from 'react'
import { TrendingDown, TrendingUp, type LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

interface MetricCardProps {
  label: string
  value: ReactNode
  unit?: string
  icon?: LucideIcon
  accent?: Accent
  /** Change versus the previous period. Sign drives the arrow and colour. */
  delta?: number
  deltaLabel?: string
  /** For metrics where down is good (body weight when cutting, resting HR...). */
  invertDelta?: boolean
  footer?: ReactNode
  className?: string
}

/** The headline number primitive - one big, scannable figure per card. */
export function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
  accent = 'brand',
  delta,
  deltaLabel,
  invertDelta = false,
  footer,
  className,
}: MetricCardProps) {
  const hasDelta = typeof delta === 'number' && delta !== 0
  const isGood = hasDelta && (invertDelta ? delta < 0 : delta > 0)
  const DeltaIcon = hasDelta && delta > 0 ? TrendingUp : TrendingDown

  return (
    <div className={cn('rounded-lg border border-line bg-surface-card p-5 shadow-card', className)}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-label text-ink-muted">{label}</p>
        {Icon && (
          <span
            className={cn(
              'flex size-8 shrink-0 items-center justify-center rounded-md',
              accentBg[accent],
              accentText[accent],
            )}
          >
            <Icon size={16} aria-hidden />
          </span>
        )}
      </div>

      <p className="tabular mt-3 flex items-baseline gap-1.5 text-metric text-ink">
        {value}
        {unit && <span className="text-section font-medium text-ink-muted">{unit}</span>}
      </p>

      {(hasDelta || footer) && (
        <div className="mt-3 flex items-center gap-2 text-meta">
          {hasDelta && (
            <span
              className={cn(
                'inline-flex items-center gap-1 font-medium',
                isGood ? 'text-success' : 'text-danger',
              )}
            >
              <DeltaIcon size={13} aria-hidden />
              <span className="tabular">
                {delta > 0 ? '+' : ''}
                {delta}
              </span>
            </span>
          )}
          {deltaLabel && <span className="text-ink-subtle">{deltaLabel}</span>}
          {footer}
        </div>
      )}
    </div>
  )
}
