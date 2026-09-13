import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { accentStroke, type Accent } from '../../navigation'
import { axisTick, gridStroke, tooltipStyles } from './chartTheme'

export interface TrendPoint {
  label: string
  value: number
}

interface TrendChartProps {
  data: TrendPoint[]
  accent?: Accent
  height?: number
  /** Appended in the tooltip, e.g. "h" for study hours. */
  unit?: string
  name?: string
}

/** Single-series trend over time - discipline, study hours, volume, weight. */
export function TrendChart({
  data,
  accent = 'brand',
  height = 240,
  unit = '',
  name = 'Value',
}: TrendChartProps) {
  const reducedMotion = usePrefersReducedMotion()
  const colour = accentStroke[accent]
  const gradientId = `trend-${accent}`

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colour} stopOpacity={0.35} />
            <stop offset="100%" stopColor={colour} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={gridStroke} vertical={false} />
        <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={false} />
        <YAxis tick={axisTick} tickLine={false} axisLine={false} width={44} />
        <Tooltip {...tooltipStyles} formatter={(value) => [`${value}${unit}`, name]} />
        <Area
          type="monotone"
          dataKey="value"
          name={name}
          stroke={colour}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive={!reducedMotion}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
