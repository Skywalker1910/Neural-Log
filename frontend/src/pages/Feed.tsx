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
import './feed.css'

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
  const words = [report.summary, ...report.strengths.map((item) => item.body), ...report.opportunities.map((item) => item.body), ...report.next_steps.map((item) => item.body)].join(' ').split(/\s+/).length
  return <article className="weekly-article" aria-label={report.title} id={`edition-${post.week_end}`}>
    <header className="edition-masthead">
      <span>Neural Log / The weekly letter</span>
      <time dateTime={post.week_end}>{shortDate(post.snapshot.start)} – {shortDate(post.week_end)}</time>
    </header>
    <div className="edition-lead">
      <p className="edition-eyebrow">Personal progress · Weekly perspective</p>
      <h2>{report.title}</h2>
      <p className="edition-deck">{report.summary}</p>
      <div className="edition-byline"><Sparkles size={15} aria-hidden /><span>Written by your AI assistant</span><span>·</span><span>{Math.max(1, Math.ceil(words / 200))} min read</span><span className="edition-private">Private to you</span></div>
    </div>
    <div className="edition-body">
      <div className="edition-columns">
      <section>
        <h3 className="edition-section-title"><Check size={16} className="text-lifestyle" /> What’s working</h3>
        <div className="edition-observations">{report.strengths.map((item, index) => <div key={index}><h4>{item.title}</h4><p>{item.body}</p></div>)}</div>
      </section>
      <section>
        <h3 className="edition-section-title"><Lightbulb size={16} className="text-goals" /> Room to grow</h3>
        <div className="edition-observations">{report.opportunities.map((item, index) => <div key={index}><h4>{item.title}</h4><p>{item.body}</p></div>)}</div>
      </section>
      </div>
      <section className="edition-evidence">
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
        <div className="space-y-2">{report.next_steps.map((item, index) => <Link key={index} to={`/${item.workspace}`} className="edition-action group flex items-start gap-3 border-b border-line py-4">
          <span className="text-caption text-brand">0{index + 1}</span><div className="flex-1"><p className="text-label text-ink">{item.title}</p><p className="mt-1 text-meta leading-6 text-ink-muted">{item.body}</p><p className="mt-2 text-caption capitalize text-ink-subtle">Open {item.workspace}</p></div><ArrowUpRight size={16} className="shrink-0 text-ink-subtle group-hover:text-brand" />
        </Link>)}</div>
      </section>
      <p className="edition-note">{report.coverage_note}</p>
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
    <PageHeader title="The weekly letter" description="Your private feed. A little perspective on the week you lived, from the days you recorded." icon={Sparkles} accent="brand" />
    <QueryBoundary query={feed} loading={<SkeletonGrid />}>{(response) => <div className="mx-auto grid max-w-6xl gap-6 xl:grid-cols-[minmax(0,720px)_240px]">
      <div className="min-w-0 space-y-10">
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
        {response.posts.length > 0 && <nav aria-label="Past editions" className="edition-archive"><h3>On your reading list</h3>{response.posts.map((post) => <a key={post.id} href={`#edition-${post.week_end}`}><span>{shortDate(post.week_end)}</span>{post.report.title}</a>)}</nav>}
      </div></aside>
    </div>}</QueryBoundary>
  </>
}
