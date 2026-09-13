import type { CSSProperties } from 'react'

import { cn } from '../../lib/cn'

interface SkeletonProps {
  className?: string
  style?: CSSProperties
}

/** Placeholder block for loading states. Pulse is disabled under reduced-motion. */
export function Skeleton({ className, style }: SkeletonProps) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-surface-raised', className)}
      style={style}
      aria-hidden
    />
  )
}

/** Card-shaped loading placeholder, sized to match MetricCard. */
export function SkeletonCard() {
  return (
    <div className="rounded-lg border border-line bg-surface-card p-5">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-4 h-9 w-32" />
      <Skeleton className="mt-3 h-3 w-20" />
    </div>
  )
}

export function SkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {Array.from({ length: count }, (_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}
