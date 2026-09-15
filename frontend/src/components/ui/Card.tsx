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
        // min-w-0 because a grid or flex item defaults to min-width:auto, which
        // means "never shrink below your content". A Card holding a DataTable
        // then widens past the viewport and scrolls the whole page sideways -
        // the table's own overflow-x-auto never gets a chance to engage. This
        // has now been the cause three times (R5, R6, R8), so it is fixed here
        // rather than at the call site again.
        'min-w-0',
        // Quiet hover: the border warms slightly so a dense dashboard still
        // responds to the cursor without cards jumping around.
        'transition-colors duration-200 ease-apple hover:border-line-strong',
        className,
      )}
    >
      {hasHeader && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-6 py-5">
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
      <div className={cn('px-6 py-5', bodyClassName)}>{children}</div>
    </section>
  )
}
