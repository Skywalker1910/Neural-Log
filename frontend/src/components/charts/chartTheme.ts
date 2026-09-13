import type { CSSProperties } from 'react'

/** Shared chart chrome so every chart in the app reads as the same system. */
export const axisTick = { fill: 'var(--color-ink-muted)', fontSize: 12 } as const

export const gridStroke = 'var(--color-line)'

export const tooltipStyles = {
  contentStyle: {
    background: 'var(--color-surface-overlay)',
    border: '1px solid var(--color-line-strong)',
    borderRadius: 'var(--radius-md)',
    fontSize: 13,
    boxShadow: 'var(--shadow-raised)',
  } satisfies CSSProperties,
  labelStyle: { color: 'var(--color-ink)', fontWeight: 600 } satisfies CSSProperties,
  itemStyle: { color: 'var(--color-ink-muted)' } satisfies CSSProperties,
  cursor: { stroke: 'var(--color-line-strong)' },
} as const
