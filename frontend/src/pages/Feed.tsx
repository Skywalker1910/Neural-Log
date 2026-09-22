import { useState } from 'react'
import { BarChart3, CalendarDays, Dumbbell, Sparkles } from 'lucide-react'

import { useWeeklyFeed } from '../api/queries'
import { TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Card } from '../components/ui/Card'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { todayISO, shortDate, shiftISO } from '../lib/date'

function hours(minutes: number | null | undefined) {
  if (minutes == null) return '—'
  return `${Math.floor(minutes / 60)}h ${String(Math.round(minutes % 60)).padStart(2, '0')}m`
}

export function Feed() {
  const [end, setEnd] = useState(todayISO)
  const feed = useWeeklyFeed(end)
  return (
    <>
      <PageHeader
        title="Weekly feed"
        description="A weekly briefing from what you actually logged. Missing days stay unknown."
        icon={Sparkles} accent="brand"
        actions={<div className="flex items-center gap-2">
          <button type="button" onClick={() => setEnd((value) => shiftISO(value, -7))}
                  className="rounded-pill border border-line px-3 py-1.5 text-meta text-ink-muted hover:text-ink">Earlier</button>
          <input type="date" value={end} onChange={(event) => setEnd(event.target.value)}
                 className="rounded-md border border-line bg-surface-card px-2 py-1.5 text-meta text-ink" />
        </div>}
      />
      <QueryBoundary query={feed} loading={<SkeletonGrid />}>
        {(data) => <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label="Sessions" value={data.totals.training_sessions ?? 0} icon={Dumbbell} accent="fitness" />
            <StatCard label="Average sleep" value={hours(data.totals.avg_sleep_minutes)} icon={CalendarDays} accent="recovery" />
            <StatCard label="Average protein" value={data.totals.avg_protein_g == null ? '—' : `${Math.round(data.totals.avg_protein_g)}g`} icon={BarChart3} accent="lifestyle" />
            <StatCard label="Average steps" value={data.totals.avg_steps?.toLocaleString() ?? '—'} icon={Sparkles} accent="learning" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Food and recovery" subtitle="Daily observations; gaps are not zeros" icon={BarChart3} accent="lifestyle">
              <TrendChart data={data.days.map((day) => ({ label: shortDate(day.date), value: day.calories }))} name="Calories" unit=" kcal" accent="lifestyle" height={220} />
            </Card>
            <Card title="Training volume" subtitle={`${data.totals.working_sets ?? 0} working sets this week`} icon={Dumbbell} accent="fitness">
              <TrendChart data={data.days.map((day) => ({ label: shortDate(day.date), value: day.volume || null }))} name="Volume" unit=" kg" accent="fitness" height={220} />
            </Card>
          </div>
          <Card title="The week at a glance" icon={CalendarDays} accent="brand">
            <div className="overflow-x-auto"><table className="w-full min-w-[42rem] text-left text-meta"><thead className="text-caption uppercase tracking-wide text-ink-subtle"><tr><th>Date</th><th>Calories</th><th>Protein</th><th>Sleep</th><th>Steps</th><th>Sets</th></tr></thead>
              <tbody>{data.days.map((day) => <tr key={day.date} className="border-t border-line text-ink-muted"><td className="py-2 text-ink">{shortDate(day.date)}</td><td>{day.calories?.toLocaleString() ?? '—'}</td><td>{day.protein_g == null ? '—' : `${Math.round(day.protein_g)}g`}</td><td>{hours(day.sleep_minutes)}</td><td>{day.steps?.toLocaleString() ?? '—'}</td><td>{day.sets || '—'}</td></tr>)}</tbody>
            </table></div>
          </Card>
          <div className="grid gap-3 lg:grid-cols-3">{data.insights.map((insight) => <Card key={insight.title} title={insight.title} accent={insight.tone === 'success' ? 'lifestyle' : insight.tone === 'warning' ? 'discipline' : 'brand'}><p className="text-meta text-ink-muted">{insight.body}</p></Card>)}</div>
        </div>}
      </QueryBoundary>
    </>
  )
}
