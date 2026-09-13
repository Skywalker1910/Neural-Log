import type { ButtonHTMLAttributes } from 'react'
import { LoaderCircle, type LucideIcon } from 'lucide-react'

import { cn } from '../../lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand text-white hover:bg-brand-hover border-transparent',
  secondary: 'bg-surface-raised text-ink border-line hover:border-line-strong hover:bg-surface-overlay',
  ghost: 'bg-transparent text-ink-muted border-transparent hover:bg-surface-raised hover:text-ink',
  danger: 'bg-transparent text-danger border-danger/40 hover:bg-danger/10',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-meta gap-1.5',
  md: 'h-10 px-4 text-label gap-2',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: LucideIcon
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
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
        'inline-flex items-center justify-center rounded-md border font-medium',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <LoaderCircle size={size === 'sm' ? 14 : 16} className="animate-spin" aria-hidden />
      ) : (
        Icon && <Icon size={size === 'sm' ? 14 : 16} aria-hidden />
      )}
      {children}
    </button>
  )
}
