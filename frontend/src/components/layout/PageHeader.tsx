import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

interface PageHeaderProps {
  title: string
  description?: ReactNode
  icon?: LucideIcon
  accent?: Accent
  actions?: ReactNode
}

export function PageHeader({ title, description, icon: Icon, accent = 'brand', actions }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-center gap-3">
        {Icon && (
          <span
            className={cn(
              'flex size-11 shrink-0 items-center justify-center rounded-lg',
              accentBg[accent],
              accentText[accent],
            )}
          >
            <Icon size={22} aria-hidden />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-heading text-ink">{title}</h1>
          {description && <p className="mt-0.5 text-label text-ink-muted">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
