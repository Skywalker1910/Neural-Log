import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, ChartNoAxesCombined, Check, Lightbulb, RefreshCw, Sparkles } from 'lucide-react'
import { Link } from 'react-router'

import { useFeedPosts, useWriteWeeklyPost } from '../api/feed'
import type { WeeklyFeedDay, WeeklyPost } from '../api/types'
import { TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Button } from '../components/ui/Button'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { shortDate } from '../lib/date'
import type { Accent } from '../navigation'

const METRICS: { key: keyof WeeklyFeedDay; label: string; unit: string; accent: Accent }[] = [
  { key: 'protein_g', label: 'Protein', unit: ' g', accent: 'lifestyle' },
  { key: 'calories', label: 'Calories', unit: ' kcal', accent: 'lifestyle' },
  { key: 'sets', label: 'Training', unit: ' sets', accent: 'fitness' },
  { key: 'sleep_minutes', label: 'Sleep', unit: ' min', accent: 'recovery' },
  { key: 'steps', label: 'Steps', unit: ' steps', accent: 'learning' },
  { key: 'water_ml', label: 'Water', unit: ' ml', accent: 'lifestyle' },
  { key: 'study_minutes', label: 'Learning', unit: ' min', accent: 'learning' },
]

function WeeklyArticle({ post }: { post: WeeklyPost }) {
  const [metricIndex, setMetricIndex] = useState(0)
  const write = useWriteWeeklyPost()
  const metric = METRICS[metricIndex]
  const report = post.report
  return <article className="overflow-hidden rounded-2xl border border-line bg-surface-card" aria-label={report.title}>
    <header className="flex items-center gap-3 px-5 py-4 sm:px-7">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand"><Sparkles size={19} /></span>
      <div className="flex-1"><p className="text-label font-semibold text-ink">Neural Log <span className="ml-1 text-caption font-normal text-ink-subtle">AI weekly review</span></p><p className="mt-0.5 text-caption text-ink-subtle">{shortDate(post.snapshot.start)} – {shortDate(post.week_end)} · Private to you</p></div>
      <span className="hidden rounded-full border border-line px-2 py-1 text-caption text-ink-muted sm:block">Weekly edition</span>
    </header>
    <div className="relative overflow-hidden border-y border-line bg-gradient-to-br from-brand-muted via-surface-card to-surface-base px-6 py-9 sm:px-8 sm:py-12">
      <div aria-hidden className="absolute -right-10 -top-12 size-56 rounded-full border-[30px] border-brand/5" />
      <p className="relative text-caption uppercase tracking-[.25em] text-brand">A moment to look back</p>
      <h2 className="relative mt-4 max-w-xl font-serif text-3xl leading-tight text-ink sm:text-4xl">{report.title}</h2>
      <p className="relative mt-5 max-w-xl text-label leading-7 text-ink-muted">{report.summary}</p>
    </div>
    <div className="space-y-7 p-5 sm:p-7">
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-label font-semibold text-ink"><Check size={16} className="text-lifestyle" /> What’s working</h3>
        <div className="space-y-3">{report.strengths.map((item, index) => <div key={index} className="border-l-2 border-lifestyle/40 pl-4"><h4 className="text-label text-ink">{item.title}</h4><p className="mt-1 text-meta leading-6 text-ink-muted">{item.body}</p></div>)}</div>
      </section>
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-label font-semibold text-ink"><Lightbulb size={16} className="text-goals" /> Room to grow</h3>
        <div className="space-y-3">{report.opportunities.map((item, index) => <div key={index} className="border-l-2 border-goals/40 pl-4"><h4 className="text-label text-ink">{item.title}</h4><p className="mt-1 text-meta leading-6 text-ink-muted">{item.body}</p></div>)}</div>
      </section>
      <section className="rounded-xl border border-line bg-surface-base/40 p-4">
        <h3 className="mb-3 flex items-center gap-2 text-label text-ink"><ChartNoAxesCombined size={16} /> Your week in numbers</h3>
        <div className="mb-3 flex flex-wrap gap-1.5" aria-label="Chart metric">{METRICS.map((item, index) => <button type="button" key={item.key} aria-pressed={index === metricIndex} onClick={() => setMetricIndex(index)} className={`rounded-full px-3 py-1.5 text-caption ${metricIndex === index ? 'bg-surface-overlay text-ink' : 'text-ink-subtle hover:text-ink'}`}>{item.label}</button>)}</div>
        <TrendChart data={post.snapshot.days.map((day) => ({ label: shortDate(day.date), value: metric.key === 'sets' && !day.sessions ? null : typeof day[metric.key] === 'number' ? day[metric.key] as number : null }))} name={metric.label} unit={metric.unit} accent={metric.accent} height={180} />
        <details className="mt-3 text-caption text-ink-muted"><summary className="cursor-pointer py-2">View recorded data</summary>
          <div className="overflow-x-auto"><table className="w-full min-w-[560px] text-left text-caption">
            <caption className="pb-3 text-left text-ink-subtle">Snapshot used for this review. A dash means no observation.</caption>
            <thead><tr>{['Day', 'kcal', 'Protein (g)', 'Sleep (min)', 'Steps', 'Water (ml)', 'Sets'].map((heading) => <th scope="col" key={heading} className="py-2 pr-3 font-medium">{heading}</th>)}</tr></thead>
            <tbody>{post.snapshot.days.map((day) => <tr key={day.date} className="border-t border-line"><th scope="row" className="py-2 pr-3 font-normal">{shortDate(day.date)}</th>{[day.calories, day.protein_g, day.sleep_minutes, day.steps, day.water_ml, day.sessions ? day.sets : null].map((value, index) => <td key={index} className="pr-3 tabular-nums">{value?.toLocaleString() ?? '—'}</td>)}</tr>)}</tbody>
          </table></div>
        </details>
      </section>
      <section>
        <h3 className="mb-3 text-label font-semibold text-ink">Take one small step</h3>
        <div className="space-y-2">{report.next_steps.map((item, index) => <Link key={index} to={`/${item.workspace}`} className="group flex items-start gap-3 rounded-lg border border-line p-4 transition-colors hover:border-brand/50">
          <span className="text-caption text-brand">0{index + 1}</span><div className="flex-1"><p className="text-label text-ink">{item.title}</p><p className="mt-1 text-meta leading-6 text-ink-muted">{item.body}</p><p className="mt-2 text-caption capitalize text-ink-subtle">Open {item.workspace}</p></div><ArrowUpRight size={16} className="shrink-0 text-ink-subtle group-hover:text-brand" />
        </Link>)}</div>
      </section>
      <p className="text-caption leading-5 text-ink-subtle">{report.coverage_note}</p>
    </div>
    <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-3 text-caption text-ink-subtle">
      <time dateTime={`${post.generated_at.replace(' ', 'T')}Z`}>Written {new Date(`${post.generated_at.replace(' ', 'T')}Z`).toLocaleDateString()}</time>
      <button type="button" disabled={write.isPending} onClick={() => write.mutate({ end: post.week_end, refresh: true })} className="flex items-center gap-2 py-2 hover:text-ink"><RefreshCw size={13} className={write.isPending ? 'animate-spin' : ''} />{write.isPending ? 'Updating review…' : 'Update with latest logs'}</button>
      {write.error && <p role="alert" className="w-full text-danger">{write.error.message}</p>}
    </footer>
  </article>
}

export function Feed() {
  const feed = useFeedPosts()
  const write = useWriteWeeklyPost()
  const attempted = useRef<string | null>(null)
  const [selectedEnd, setSelectedEnd] = useState('')
  const data = feed.data
  useEffect(() => {
    if (!data?.configured || !data.has_data || write.isPending || attempted.current === data.latest_week_end || data.posts.some((post) => post.week_end === data.latest_week_end)) return
    attempted.current = data.latest_week_end
    write.mutate({ end: data.latest_week_end })
  }, [data, write])
  return <>
    <PageHeader title="Your weekly feed" description="A little perspective on the week you lived. Written for you, from the days you recorded." icon={Sparkles} accent="brand" />
    <QueryBoundary query={feed} loading={<SkeletonGrid />}>{(response) => <div className="mx-auto grid max-w-6xl gap-6 xl:grid-cols-[minmax(0,720px)_240px]">
      <div className="min-w-0 space-y-6">
        {write.isPending && <div role="status" className="flex items-center gap-3 rounded-xl border border-brand/30 bg-brand-muted/30 p-5 text-label text-ink"><Sparkles size={18} className="animate-pulse text-brand" />Your weekly review is being written…</div>}
        {write.error && <div role="alert" className="rounded-xl border border-line p-5 text-meta text-ink-muted"><p>{write.error.message}</p><button type="button" className="mt-3 text-brand" onClick={() => write.mutate({ end: selectedEnd || response.latest_week_end })}>Try again</button></div>}
        {response.posts.length === 0 && !write.isPending && <div className="rounded-2xl border border-line bg-surface-card p-8 text-center"><Sparkles size={32} className="mx-auto text-brand" /><h2 className="mt-5 font-serif text-2xl text-ink">Your story is taking shape.</h2><p className="mx-auto mt-3 max-w-md text-label leading-7 text-ink-muted">{!response.configured ? 'AI weekly reviews will be available when the assistant is configured. Your daily logs are ready whenever you are.' : !response.has_data ? 'Record meals, movement, sleep, or learning. Your first review will be ready after a week with recorded activity has ended.' : 'Your first weekly review brings your recorded days together.'}</p><Link to="/today" className="mt-5 inline-block text-label text-brand">Go to today’s log →</Link></div>}
        {response.posts.map((post) => <WeeklyArticle key={post.id} post={post} />)}
      </div>
      <aside><div className="rounded-xl border border-line p-5 xl:sticky xl:top-24">
        <p className="text-caption uppercase tracking-widest text-brand">The weekly ritual</p><h2 className="mt-3 font-serif text-xl text-ink">Reflect. Adjust. Repeat.</h2>
        <p className="mt-3 text-meta leading-6 text-ink-muted">On your first visit each week, the assistant reviews the previous Monday–Sunday. Each post is saved here for you to revisit.</p>
        <p className="mt-3 text-caption leading-5 text-ink-subtle">Reviews use your recorded activity and the previous week for context. Personal journal text stays out of the review.</p>
        {response.configured && <div className="mt-5 border-t border-line pt-4"><label className="flex flex-col gap-2 text-caption text-ink-muted">Review a week ending Sunday<input aria-label="Review week ending" type="date" min="2000-01-02" step={7} max={response.latest_week_end} value={selectedEnd || response.latest_week_end} onChange={(event) => setSelectedEnd(event.target.value)} className="min-w-0 rounded-md border border-line bg-surface-card p-2 text-label text-ink" /></label>
          <Button className="mt-3 w-full" icon={Sparkles} disabled={write.isPending} onClick={() => write.mutate({ end: selectedEnd || response.latest_week_end })}>Write review</Button>
        </div>}
        <Link to="/analytics" className="mt-5 flex items-center gap-2 text-meta text-ink-muted">Explore all analytics <ArrowUpRight size={14} /></Link>
      </div></aside>
    </div>}</QueryBoundary>
  </>
}
