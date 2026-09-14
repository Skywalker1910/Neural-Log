import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

interface StatCardProps {
  label: string
  value: ReactNode
  icon?: LucideIcon
  accent?: Accent
  hint?: string
  className?: string
}

/** Compact inline statistic - for dense rows where MetricCard would be too loud. */
export function StatCard({ label, value, icon: Icon, accent = 'brand', hint, className }: StatCardProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 rounded-md border border-line bg-surface-card px-4 py-3',
        className,
      )}
    >
      {Icon && (
        <span
          className={cn(
            'flex size-9 shrink-0 items-center justify-center rounded-md',
            accentBg[accent],
            accentText[accent],
          )}
        >
          <Icon size={17} aria-hidden />
        </span>
      )}
      {/*
        The value is the whole point of the card, so it gets the space and the
        hint gives way. Previously the hint was `shrink-0` and the value could
        truncate, which rendered a 16,710kg total as "1".
      */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-meta text-ink-muted">{label}</p>
        <p className="tabular truncate text-section text-ink">{value}</p>
        {hint && <p className="truncate text-caption text-ink-subtle">{hint}</p>}
      </div>
    </div>
  )
}
