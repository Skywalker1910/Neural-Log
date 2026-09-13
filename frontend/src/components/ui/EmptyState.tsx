import type { ReactNode } from 'react'
import { Inbox, type LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: ReactNode
  /** Give people the action that fills the void, not just an apology. */
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center px-6 py-12 text-center', className)}>
      <span className="flex size-12 items-center justify-center rounded-full border border-line bg-surface-raised text-ink-subtle">
        <Icon size={22} aria-hidden />
      </span>
      <h3 className="mt-4 text-section text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-label text-ink-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
