import { lazy, Suspense, type ComponentProps } from 'react'

import { Skeleton } from '../ui/Skeleton'

/**
 * Recharts is ~400kB of the bundle, and most pages never draw a chart. These
 * wrappers split it into its own chunk that loads on first render, so the shell
 * stays light (brief §51). Consumers use them like ordinary components.
 */
const LazyAttributeRadar = lazy(() =>
  import('./AttributeRadar').then((module) => ({ default: module.AttributeRadar })),
)

const LazyTrendChart = lazy(() =>
  import('./TrendChart').then((module) => ({ default: module.TrendChart })),
)

function ChartFallback({ height }: { height: number }) {
  return <Skeleton className="w-full rounded-md" style={{ height }} />
}

export function AttributeRadar(props: ComponentProps<typeof LazyAttributeRadar>) {
  return (
    <Suspense fallback={<ChartFallback height={props.height ?? 320} />}>
      <LazyAttributeRadar {...props} />
    </Suspense>
  )
}

export function TrendChart(props: ComponentProps<typeof LazyTrendChart>) {
  return (
    <Suspense fallback={<ChartFallback height={props.height ?? 240} />}>
      <LazyTrendChart {...props} />
    </Suspense>
  )
}

/* CalendarHeatmap is a CSS grid of divs, not a Recharts chart - it carries no
   library weight, so lazy-loading it would add a network round trip and a
   skeleton flash to save nothing. Re-exported here only so every chart has one
   import path. */
export { CalendarHeatmap } from './CalendarHeatmap'

export type { AttributeDatum } from './AttributeRadar'
export type { TrendPoint } from './TrendChart'
