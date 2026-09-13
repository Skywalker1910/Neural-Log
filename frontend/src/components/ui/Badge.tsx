import type { ReactNode } from 'react'

import { cn } from '../../lib/cn'

type Tone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info'

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-raised text-ink-muted border-line',
  brand: 'bg-brand/12 text-brand border-brand/30',
  success: 'bg-success/12 text-success border-success/30',
  warning: 'bg-warning/12 text-warning border-warning/30',
  danger: 'bg-danger/12 text-danger border-danger/30',
  info: 'bg-info/12 text-info border-info/30',
}

interface BadgeProps {
  tone?: Tone
  className?: string
  children: ReactNode
}

export function Badge({ tone = 'neutral', className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-meta font-medium',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
