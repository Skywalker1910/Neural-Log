import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  icon?: LucideIcon
  accent?: Accent
  /** Rendered on the right of the header - usually a Button or a filter. */
  action?: ReactNode
  className?: string
  bodyClassName?: string
  children?: ReactNode
}

/** The single surface primitive every dashboard card is built from. */
export function Card({
  title,
  subtitle,
  icon: Icon,
  accent = 'brand',
  action,
  className,
  bodyClassName,
  children,
}: CardProps) {
  const hasHeader = Boolean(title || subtitle || action || Icon)

  return (
    <section
      className={cn(
        'rounded-lg border border-line bg-surface-card shadow-card',
        // Quiet hover: the border warms slightly so a dense dashboard still
        // responds to the cursor without cards jumping around.
        'transition-colors duration-200 hover:border-line-strong',
        className,
      )}
    >
      {hasHeader && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            {Icon && (
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-md',
                  accentBg[accent],
                  accentText[accent],
                )}
              >
                <Icon size={18} aria-hidden />
              </span>
            )}
            <div className="min-w-0">
              {title && <h2 className="truncate text-section text-ink">{title}</h2>}
              {subtitle && <p className="truncate text-meta text-ink-muted">{subtitle}</p>}
            </div>
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={cn('px-5 py-4', bodyClassName)}>{children}</div>
    </section>
  )
}
