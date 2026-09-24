import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { CalendarDays, ChartLine, Download, Target } from 'lucide-react'

import { useAnalytics } from '../api/queries'
import type { AnalyticsMetric, AnalyticsPeriod } from '../api/types'
import { AttributeRadar, CalendarHeatmap, TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { MetricCard } from '../components/ui/MetricCard'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { shortDate } from '../lib/date'

const PERIODS: { value: AnalyticsPeriod; label: string }[] = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '365', label: 'Year' },
  { value: 'all', label: 'All time' },
]

/**
 * Render a metric in its own terms.
 *
 * Minutes are the obvious trap: the API stores them because that is what gets
 * logged, but "470 min" of sleep is a number you have to do arithmetic on before
 * it means anything, and "7h 50m" is not.
 */
function format(metric: AnalyticsMetric, raw: number | null): string {
  if (raw === null) return '—'
  if (metric.key === 'sleep_minutes' || metric.key === 'study_minutes') {
    const hours = Math.floor(raw / 60)
    const minutes = Math.round(raw % 60)
    return hours ? `${hours}h ${minutes ? `${minutes}m` : ''}`.trim() : `${minutes}m`
  }
  return raw.toLocaleString(undefined, { maximumFractionDigits: 1 }) + metric.unit
}

/**
 * How to read the number above it.
 *
 * An average over 9 of 30 days is a different claim from an average over 30, and
 * the figure alone cannot tell you which you are looking at. This is the line
 * that keeps the dashboard honest rather than merely confident.
 */
function coverage(metric: AnalyticsMetric): string {
  if (metric.observed_days === 0) return 'Nothing logged yet'
  const noun = metric.aggregate === 'avg' ? 'averaged over' : 'across'
  return `${noun} ${metric.observed_days} of ${metric.days} days`
}

function PeriodPicker({
  value,
  onChange,
}: {
  value: AnalyticsPeriod
  onChange: (next: AnalyticsPeriod) => void
}) {
  return (
    <div
      role="tablist"
      aria-label="Period"
      className="flex max-w-full flex-wrap rounded-md border border-line bg-surface-card p-0.5"
    >
      {PERIODS.map((period) => {
        const active = period.value === value
        return (
          <button
            key={period.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(period.value)}
            className={cn(
              'shrink-0 rounded-pill px-3.5 py-1.5 text-meta font-medium transition-colors duration-200 ease-apple',
              active ? 'bg-surface-raised text-ink' : 'text-ink-muted hover:text-ink',
            )}
          >
            {period.label}
          </button>
        )
      })}
    </div>
  )
}

export function Analytics() {
  const [period, setPeriod] = useState<AnalyticsPeriod>('30')
  const [focus, setFocus] = useState('daily_score')
  const query = useAnalytics(period)
  const navigate = useNavigate()

  const data = query.data
  const selected = useMemo(
    () => data?.metrics.find((metric) => metric.key === focus) ?? data?.metrics[0],
    [data, focus],
  )

  const trend = useMemo(
    () =>
      selected?.series.map((point) => ({
        label: shortDate(point.date),
        value: point.value,
      })) ?? [],
    [selected],
  )

  const radar = useMemo(
    () =>
      data?.attributes
        .filter((attribute) => attribute.score !== null)
        .map((attribute) => ({
          attribute: attribute.attribute,
          value: attribute.score ?? 0,
          previous: attribute.previous ?? undefined,
        })) ?? [],
    [data],
  )

  return (
    <>
      <PageHeader
        illustration="analytics"
        title="Analytics"
        description="Long-range trends across every workspace, measured only on the days you logged."
        icon={ChartLine}
        accent="learning"
        actions={
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <PeriodPicker value={period} onChange={setPeriod} />
            <Button
              variant="secondary"
              icon={Download}
              onClick={() => {
                window.location.href = '/api/export/excel'
              }}
            >
              Export
            </Button>
          </div>
        }
      />

      <QueryBoundary query={query} loading={<SkeletonGrid />}>
        {(payload) => (
          <RevealGroup className="flex flex-col gap-4" step={0.05}>
            <Reveal>
              <p className="text-meta text-ink-subtle">
                {payload.range.label} — {shortDate(payload.range.start)} to{' '}
                {shortDate(payload.range.end)}. Compared against{' '}
                {shortDate(payload.previous.start)} to {shortDate(payload.previous.end)}.{' '}
                {payload.days_logged} of {payload.range.days} days logged.
              </p>
            </Reveal>

            <Reveal>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {payload.metrics.map((metric) => (
                  <MetricCard
                    key={metric.key}
                    label={metric.label}
                    value={format(metric, metric.value)}
                    accent={metric.accent}
                    // Only a real comparison gets an arrow. Passing 0 when the
                    // previous window was empty would render "no change", which
                    // is a claim we cannot make.
                    delta={metric.delta_pct ?? undefined}
                    deltaUnit="%"
                    deltaLabel="vs previous"
                    footer={
                      <span className="text-caption uppercase tracking-wide text-ink-subtle">
                        {coverage(metric)}
                      </span>
                    }
                  />
                ))}
              </div>
            </Reveal>

            <Reveal>
              <Card
                title={selected?.label ?? 'Trend'}
                subtitle={selected ? coverage(selected) : undefined}
                icon={ChartLine}
                accent={selected?.accent ?? 'learning'}
                action={
                  <select
                    value={selected?.key}
                    onChange={(event) => setFocus(event.target.value)}
                    aria-label="Metric to chart"
                    className="h-8 rounded-md border border-line bg-surface-raised px-2 text-meta text-ink"
                  >
                    {payload.metrics.map((metric) => (
                      <option key={metric.key} value={metric.key}>
                        {metric.label}
                      </option>
                    ))}
                  </select>
                }
              >
                {selected && selected.observed_days > 0 ? (
                  <TrendChart
                    data={trend}
                    accent={selected.accent}
                    name={selected.label}
                    unit={selected.unit}
                    domain={selected.domain ?? undefined}
                    height={260}
                  />
                ) : (
                  <EmptyState
                    icon={ChartLine}
                    title="Nothing logged for this yet"
                    description="Log a few days and the line starts drawing. Gaps stay gaps — a day you didn't log isn't a zero."
                  />
                )}
              </Card>
            </Reveal>

            <div className="grid gap-4 lg:grid-cols-2">
              <Reveal>
                <Card
                  title="Adherence"
                  subtitle="How much of your Path you completed, day by day"
                  icon={CalendarDays}
                  accent="lifestyle"
                >
                  {payload.days_logged > 0 ? (
                    <CalendarHeatmap
                      cells={payload.calendar}
                      onSelect={(date) => navigate(`/today?date=${date}`)}
                    />
                  ) : (
                    <EmptyState
                      icon={CalendarDays}
                      title="No days logged in this period"
                      description="Run through your Path and the squares start filling in."
                    />
                  )}
                </Card>
              </Reveal>

              <Reveal>
                <Card
                  title="Attributes"
                  subtitle={`Now, against ${shortDate(payload.range.start)}`}
                  icon={Target}
                  accent="goals"
                >
                  {radar.length > 0 ? (
                    <>
                      <AttributeRadar data={radar} compareLabel="Period start" height={280} />
                      <div className="mt-4 flex flex-wrap gap-2">
                        {payload.attributes
                          .filter((attribute) => attribute.delta !== null && attribute.delta !== 0)
                          .map((attribute) => (
                            <Badge
                              key={attribute.attribute}
                              tone={(attribute.delta ?? 0) > 0 ? 'success' : 'warning'}
                            >
                              {attribute.attribute} {(attribute.delta ?? 0) > 0 ? '+' : ''}
                              {attribute.delta}
                            </Badge>
                          ))}
                      </div>
                    </>
                  ) : (
                    <EmptyState
                      icon={Target}
                      title="Attributes are still forming"
                      description="They need a few days of history before a score means anything."
                    />
                  )}
                </Card>
              </Reveal>
            </div>
          </RevealGroup>
        )}
      </QueryBoundary>
    </>
  )
}
