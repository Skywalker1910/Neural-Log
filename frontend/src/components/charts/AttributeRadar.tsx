import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

import { useMediaQuery } from '../../lib/useMediaQuery'
import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { axisTick, gridStroke, tooltipStyles } from './chartTheme'

/**
 * Eight axes on a phone-width card cannot fit "Consistency" either side of the
 * chart - SVG text has no wrapping or ellipsis, so it simply gets cut off. Every
 * attribute is also named in full in the badge grid beneath the chart, so
 * abbreviating here loses nothing.
 */
const NARROW = '(max-width: 640px)'

function abbreviate(label: string): string {
  return label.slice(0, 3).toUpperCase()
}

export interface AttributeDatum {
  attribute: string
  /** Normalised 0-100. */
  value: number
  /** Optional previous-period overlay ("this week vs last week"). */
  previous?: number
}

interface AttributeRadarProps {
  data: AttributeDatum[]
  height?: number
  /** Label for the comparison series, when the data carries `previous`. */
  compareLabel?: string
}

/**
 * The "your character is built by your behaviour" chart (brief §9). Shape grows
 * and shrinks with real attribute scores.
 */
export function AttributeRadar({ data, height = 320, compareLabel = 'Previous' }: AttributeRadarProps) {
  const reducedMotion = usePrefersReducedMotion()
  const narrow = useMediaQuery(NARROW)
  const hasComparison = data.some((point) => typeof point.previous === 'number')

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius={narrow ? '62%' : '72%'}>
        <PolarGrid stroke={gridStroke} />
        <PolarAngleAxis
          dataKey="attribute"
          tick={axisTick}
          tickFormatter={narrow ? abbreviate : undefined}
        />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        {hasComparison && (
          <Radar
            name={compareLabel}
            dataKey="previous"
            stroke="var(--color-ink-subtle)"
            fill="var(--color-ink-subtle)"
            fillOpacity={0.12}
            isAnimationActive={!reducedMotion}
          />
        )}
        <Radar
          name="Current"
          dataKey="value"
          stroke="var(--color-brand)"
          fill="var(--color-brand)"
          fillOpacity={0.28}
          isAnimationActive={!reducedMotion}
        />
        <Tooltip {...tooltipStyles} />
      </RadarChart>
    </ResponsiveContainer>
  )
}
