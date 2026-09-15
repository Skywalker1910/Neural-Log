import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { accentStroke, type Accent } from '../../navigation'
import { axisTick, gridStroke, tooltipStyles } from './chartTheme'

export interface TrendPoint {
  label: string
  /**
   * null is *unobserved*, not zero. Recharts breaks the line at a null, which is
   * the honest rendering: a day you did not log is a gap in what we know, and
   * plotting it at 0 would draw a crash that never happened.
   */
  value: number | null
}

interface TrendChartProps {
  data: TrendPoint[]
  accent?: Accent
  height?: number
  /** Appended in the tooltip, e.g. "h" for study hours. */
  unit?: string
  name?: string
  /**
   * Fixed y-axis range. Give this for any bounded scale - a 1-5 mood rating
   * left on Recharts' auto-domain drew an axis up to 8, which makes a good
   * week look like a mediocre one.
   */
  domain?: [number, number]
}

/**
 * Four-figure values (training volume) overflowed the axis gutter and rendered
 * as "000". Compacting at 1,000 keeps the gutter narrow without lying about the
 * number - the tooltip still shows it in full.
 */
function compact(value: number): string {
  if (Math.abs(value) < 1000) return String(value)
  const thousands = value / 1000
  return `${thousands % 1 === 0 ? thousands : thousands.toFixed(1)}k`
}

/** Single-series trend over time - discipline, study hours, volume, weight. */
export function TrendChart({
  data,
  accent = 'brand',
  height = 240,
  unit = '',
  name = 'Value',
  domain,
}: TrendChartProps) {
  const reducedMotion = usePrefersReducedMotion()
  const colour = accentStroke[accent]
  const gradientId = `trend-${accent}`

  /*
    Dots when the observations are sparse.

    A line is drawn *between* points, so with connectNulls={false} a single
    observed day surrounded by unlogged ones has nothing to connect to and
    renders as literally nothing - the chart looks empty while holding real
    data. A dot is the only way an isolated observation can be seen.

    Above the threshold they are dropped: on a dense series the dots crowd into
    a thick band and the trend gets harder to read, which is the problem they
    were added to solve, inverted.
  */
  const observed = data.reduce((count, point) => count + (point.value === null ? 0 : 1), 0)
  const sparse = observed <= 12

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colour} stopOpacity={0.35} />
            <stop offset="100%" stopColor={colour} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={gridStroke} vertical={false} />
        <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={false} />
        <YAxis
          tick={axisTick} tickLine={false} axisLine={false} width={44}
          tickFormatter={compact} domain={domain ?? ['auto', 'auto']}
          allowDecimals={!domain}
        />
        <Tooltip
          {...tooltipStyles}
          formatter={(value) => [`${Number(value).toLocaleString()}${unit}`, name]}
        />
        <Area
          type="monotone"
          dataKey="value"
          name={name}
          stroke={colour}
          strokeWidth={2}
          fill={`url(#${gradientId})`}
          isAnimationActive={!reducedMotion}
          /* Leave the gaps. connectNulls would draw a straight line across the
             days with no data, inventing a trend through them. */
          connectNulls={false}
          dot={sparse ? { r: 3, fill: colour, strokeWidth: 0 } : false}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
