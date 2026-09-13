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
      <div className="min-w-0">
        <p className="truncate text-meta text-ink-muted">{label}</p>
        <p className="tabular truncate text-section text-ink">{value}</p>
      </div>
      {hint && <p className="ml-auto shrink-0 text-meta text-ink-subtle">{hint}</p>}
    </div>
  )
}
