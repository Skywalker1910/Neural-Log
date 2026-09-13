import type { LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentText, type Accent } from '../../navigation'

const BAR_FILL: Record<Accent, string> = {
  brand: 'bg-brand',
  fitness: 'bg-fitness',
  learning: 'bg-learning',
  lifestyle: 'bg-lifestyle',
  goals: 'bg-goals',
  discipline: 'bg-discipline',
  recovery: 'bg-recovery',
}

interface ProgressCardProps {
  label: string
  value: number
  target: number
  unit?: string
  icon?: LucideIcon
  accent?: Accent
  className?: string
}

/** "Protein 142 / 165 g" with a bar - the daily-target primitive. */
export function ProgressCard({
  label,
  value,
  target,
  unit,
  icon: Icon,
  accent = 'brand',
  className,
}: ProgressCardProps) {
  const pct = target > 0 ? Math.min(100, (value / target) * 100) : 0
  const complete = value >= target && target > 0

  return (
    <div
      className={cn('rounded-md border border-line bg-surface-card px-4 py-3.5', className)}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-label text-ink-muted">
          {Icon && <Icon size={15} className={accentText[accent]} aria-hidden />}
          {label}
        </span>
        <span className="tabular text-label text-ink">
          <span className={cn(complete && accentText[accent])}>{value}</span>
          <span className="text-ink-subtle"> / {target}</span>
          {unit && <span className="text-ink-subtle"> {unit}</span>}
        </span>
      </div>

      <div
        className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-surface-raised"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-500', BAR_FILL[accent])}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
