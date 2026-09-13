import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

import { usePrefersReducedMotion } from '../../lib/usePrefersReducedMotion'
import { axisTick, gridStroke, tooltipStyles } from './chartTheme'

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
  const hasComparison = data.some((point) => typeof point.previous === 'number')

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke={gridStroke} />
        <PolarAngleAxis dataKey="attribute" tick={axisTick} />
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
