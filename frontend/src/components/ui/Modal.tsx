import { useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

import { cn } from '../../lib/cn'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  /** Rendered in the footer, right-aligned - usually Cancel + a confirm Button. */
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg'
  children?: ReactNode
}

const SIZES = {
  sm: 'max-w-md',
  md: 'max-w-xl',
  lg: 'max-w-3xl',
}

export function Modal({ open, onClose, title, description, footer, size = 'md', children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)

    // Stop the page behind the overlay from scrolling.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    panelRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
        className={cn(
          'w-full overflow-hidden rounded-t-xl border border-line bg-surface-card shadow-overlay outline-none sm:rounded-xl',
          SIZES[size],
        )}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-section text-ink">
              {title}
            </h2>
            {description && <p className="mt-1 text-meta text-ink-muted">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="-mr-1 rounded-md p-1 text-ink-subtle transition-colors hover:bg-surface-raised hover:text-ink"
          >
            <X size={18} aria-hidden />
          </button>
        </header>

        {children && <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>}

        {footer && (
          <footer className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>
        )}
      </div>
    </div>
  )
}
