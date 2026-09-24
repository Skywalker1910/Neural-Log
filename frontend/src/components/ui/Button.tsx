import type { ButtonHTMLAttributes } from 'react'
import { LoaderCircle, type LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary: 'border-transparent',
  secondary: 'bg-surface-raised text-ink border-line hover:border-line-strong hover:bg-surface-overlay',
  ghost: 'bg-transparent text-ink-muted border-transparent hover:bg-surface-raised hover:text-ink',
  danger: 'bg-transparent text-danger border-danger/40 hover:bg-danger/10',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3.5 text-meta gap-1.5',
  md: 'h-10 px-5 text-label gap-2',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: LucideIcon
  /**
   * Which side the icon sits on. 'start' reads as "this icon describes the
   * action" (a trash can, a plus); 'end' reads as "this is where it takes you",
   * which is what a forward arrow means. "→ Continue" points back at the label.
   */
  iconPosition?: 'start' | 'end'
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  iconPosition = 'start',
  loading = false,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cn(
        `app-button button-${variant}`,
        'inline-flex max-w-full items-center justify-center rounded-md border font-medium tracking-tight',
        'transition-all duration-200 ease-apple disabled:cursor-not-allowed disabled:opacity-50',
        'active:scale-[0.97] disabled:active:scale-100',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {/* The spinner always takes the icon's slot, so the label does not shift
          sideways when a button starts loading. */}
      {loading ? (
        <LoaderCircle size={size === 'sm' ? 14 : 16} className="animate-spin" aria-hidden />
      ) : (
        Icon && iconPosition === 'start' && <Icon size={size === 'sm' ? 14 : 16} aria-hidden />
      )}
      {children}
      {!loading && Icon && iconPosition === 'end' && (
        <Icon size={size === 'sm' ? 14 : 16} aria-hidden />
      )}
    </button>
  )
}
