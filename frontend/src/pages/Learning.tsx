import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import {
  BookOpen, Brain, Clock, Flame, FolderTree, Info, Layers, Pencil, Plus,
  Target, Trash2,
} from 'lucide-react'

import type {
  LearningArea, LearningSession, LearningSummary, LearningTopic,
} from '../api/types'
import {
  useDeleteArea, useDeleteSession, useDeleteTopic, useLearningAreas,
  useLearningSummary, useLearningTopics,
} from '../api/queries'
import { AreaEditor, TopicEditor } from '../components/learning/TopicEditor'
import { SessionLogger } from '../components/learning/SessionLogger'
import { TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { EmptyState } from '../components/ui/EmptyState'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { cn } from '../lib/cn'
import { shiftISO, shortDate } from '../lib/date'
import { spring } from '../lib/motion'
import { accentStroke, accentText, type Accent } from '../navigation'

const KNOWN_ACCENTS = new Set([
  'brand', 'fitness', 'learning', 'lifestyle', 'goals', 'discipline', 'recovery',
])

/** The API stores accents as free text, so narrow before indexing the palette. */
function toAccent(value: string | null | undefined): Accent {
  return KNOWN_ACCENTS.has(value ?? '') ? (value as Accent) : 'learning'
}

function hoursMinutes(minutes: number | null | undefined) {
  if (!minutes) return '0m'
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

/**
 * Where the hours actually went.
 *
 * Bars are relative to the biggest topic rather than to a target - there is no
 * "correct" split between topics, only the one you chose, and drawing it against
 * an invented target would imply otherwise.
 */
function TopicDistribution({ rows }: { rows: LearningSummary['by_topic'] }) {
  const max = Math.max(...rows.map((row) => row.minutes), 1)
  const total = rows.reduce((sum, row) => sum + row.minutes, 0)

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, index) => (
        <div key={`${row.area}-${row.topic}`} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-meta text-ink-muted"
                title={row.area ? `${row.area} · ${row.topic}` : row.topic}>
            {row.topic}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
            {/*
              Coloured from accentStroke's CSS variable rather than a Tailwind
              class: the accent is data from the server, and Tailwind only emits
              classes it can see as literal strings - `bg-${accent}` would compile
              to nothing and the bars would be invisible.
            */}
            <m.div
              className="h-full rounded-full"
              style={{ backgroundColor: accentStroke[toAccent(row.accent)] }}
              initial={{ width: 0 }}
              animate={{ width: `${(row.minutes / max) * 100}%` }}
              transition={{ ...spring.soft, delay: index * 0.04 }}
            />
          </div>
          <span className="tabular w-20 shrink-0 text-right text-meta text-ink-subtle">
            {hoursMinutes(row.minutes)}
            {total > 0 && (
              <span className="text-ink-subtle">
                {' '}({Math.round((row.minutes / total) * 100)}%)
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}

function DepthExplainer({ totals }: { totals: LearningSummary['totals'] }) {
  if (totals.depth_pct == null) {
    return (
      <p className="text-label text-ink-subtle">
        Log a few sessions with start and end times and this fills in. Below half
        an hour in the window there is not enough to characterise a pattern, so it
        stays quiet rather than reporting noise.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline gap-2">
        <span className="tabular text-metric text-ink">{totals.depth_pct}%</span>
        <span className="text-label text-ink-muted">of a deep block</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
        <m.div
          className="h-full rounded-full bg-learning"
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, totals.depth_pct)}%` }}
          transition={spring.soft}
        />
      </div>
      <p className="flex items-start gap-1.5 text-meta text-ink-subtle">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
        How long your typical uninterrupted block was, against a target of{' '}
        {totals.target_block_minutes} minutes. One long block beats several short
        ones for the same total — that difference is what Focus measures, and it
        is why sessions less than fifteen minutes apart count as one block.
      </p>
    </div>
  )
}

export function Learning() {
  const summary = useLearningSummary()
  const areas = useLearningAreas()
  const topics = useLearningTopics()

  const removeArea = useDeleteArea()
  const removeTopic = useDeleteTopic()
  const removeSession = useDeleteSession()

  const [logging, setLogging] = useState<number | null | undefined>(undefined)
  /** undefined = closed, null = creating, a row = editing it. */
  const [editingArea, setEditingArea] = useState<LearningArea | null | undefined>(undefined)
  const [editingTopic, setEditingTopic] = useState<LearningTopic | null | undefined>(undefined)

  /**
   * Days with no study are filled in as zero rather than left out.
   *
   * The endpoint only returns days that have sessions, so plotting it directly
   * draws a line straight from one study day to the next and a rest day looks
   * like continuity. Filling the gaps shows them for what they are.
   *
   * The fill runs only between the first and last logged day - extending it back
   * thirty days would invent a history of not studying before you started, which
   * is the same mistake the producers deliberately avoid.
   */
  const trend = useMemo(() => {
    const days = summary.data?.by_day ?? []
    if (days.length === 0) return []

    const minutesByDate = new Map(days.map((point) => [point.date, point.minutes]))
    const points: { label: string; value: number }[] = []

    let cursor = days[0].date
    const last = days[days.length - 1].date
    // Bounded so a corrupt date cannot spin here.
    for (let guard = 0; cursor <= last && guard < 400; guard += 1) {
      points.push({
        label: shortDate(cursor),
        value: Math.round(((minutesByDate.get(cursor) ?? 0) / 60) * 10) / 10,
      })
      cursor = shiftISO(cursor, 1)
    }
    return points
  }, [summary.data])

  const weekPct = useMemo(() => {
    const totals = summary.data?.totals
    if (!totals?.weekly_target_minutes) return 0
    return Math.min(100, (totals.this_week_minutes / totals.weekly_target_minutes) * 100)
  }, [summary.data])

  const sessionColumns: Column<LearningSession>[] = [
    {
      key: 'date',
      header: 'Date',
      render: (row) => <span className="tabular text-ink">{row.date}</span>,
    },
    {
      key: 'topic',
      header: 'Topic',
      render: (row) => (
        <span className="flex items-center gap-2">
          {row.area_name && (
            <span className={cn('text-caption', accentText[toAccent(row.area_accent)])}>
              ●
            </span>
          )}
          <span className="truncate">{row.topic_name ?? 'Unfiled'}</span>
        </span>
      ),
    },
    {
      key: 'duration',
      header: 'Time',
      align: 'right',
      render: (row) => <span className="tabular">{hoursMinutes(row.duration_minutes)}</span>,
    },
    {
      key: 'when',
      header: 'Block',
      align: 'right',
      hideBelow: 'sm',
      render: (row) => (
        <span className="tabular text-ink-subtle">
          {row.started_at && row.ended_at ? `${row.started_at}–${row.ended_at}` : '—'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) => (
        <Button
          size="sm" variant="ghost" icon={Trash2}
          aria-label={`Delete session on ${row.date}`}
          onClick={() => removeSession.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <>
      <PageHeader
        illustration="learning"
        title="Learning"
        description="Study time feeds Knowledge. How that time is shaped feeds Focus."
        icon={Brain}
        accent="learning"
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" icon={FolderTree} onClick={() => setEditingArea(null)}>
              New area
            </Button>
            <Button size="sm" variant="primary" icon={Plus} onClick={() => setLogging(null)}>
              Study session
            </Button>
          </div>
        }
      />

      <QueryBoundary query={summary} loading={<SkeletonGrid />}>
        {(data) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard
                label="This week"
                value={hoursMinutes(data.totals.this_week_minutes)}
                icon={Clock} accent="learning"
                hint={`target ${hoursMinutes(data.totals.weekly_target_minutes)}`}
              />
              <StatCard
                label="Streak"
                value={data.totals.streak_days ? `${data.totals.streak_days} days` : '—'}
                icon={Flame} accent="discipline" hint="consecutive days studied"
              />
              <StatCard
                label="Block depth"
                value={data.totals.depth_pct != null ? `${data.totals.depth_pct}%` : '—'}
                icon={Target} accent="goals" hint="what Focus measures"
              />
              <StatCard
                label="All time"
                value={hoursMinutes(data.totals.minutes)}
                icon={BookOpen} accent="learning"
                hint={`${data.totals.sessions} sessions`}
              />
            </Reveal>

            {data.totals.sessions === 0 ? (
              <Reveal>
                <EmptyState
                  icon={Brain}
                  title="Nothing studied yet"
                  description="Log a session and Knowledge stops being a guess from a checkbox. Add start and end times and Focus becomes measurable too."
                  action={
                    <Button variant="primary" icon={Plus} onClick={() => setLogging(null)}>
                      Study session
                    </Button>
                  }
                />
              </Reveal>
            ) : (
              <>
                <Reveal>
                  <Card
                    title="Weekly goal"
                    subtitle={`${hoursMinutes(data.totals.this_week_minutes)} of ${hoursMinutes(data.totals.weekly_target_minutes)}`}
                    icon={Target}
                    accent="learning"
                  >
                    <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
                      <m.div
                        className="h-full rounded-full bg-learning"
                        initial={{ width: 0 }}
                        animate={{ width: `${weekPct}%` }}
                        transition={spring.soft}
                      />
                    </div>
                  </Card>
                </Reveal>

                <Reveal>
                  <Card
                    title="Study time" subtitle="Hours per day, last 30 days"
                    icon={Clock} accent="learning"
                  >
                    <TrendChart data={trend} accent="learning" unit="h" name="Studied" />
                  </Card>
                </Reveal>

                <Reveal className="grid gap-4 lg:grid-cols-2">
                  <Card
                    title="Where the time went" subtitle="Last 30 days"
                    icon={Layers} accent="learning"
                  >
                    {data.by_topic.length === 0 ? (
                      <p className="text-label text-ink-subtle">Nothing logged yet.</p>
                    ) : (
                      <TopicDistribution rows={data.by_topic} />
                    )}
                  </Card>

                  <Card title="Block depth" icon={Target} accent="goals">
                    <DepthExplainer totals={data.totals} />
                  </Card>
                </Reveal>

                <Reveal>
                  <Card title="Recent sessions" icon={BookOpen} accent="learning">
                    <DataTable
                      columns={sessionColumns}
                      rows={data.recent}
                      rowKey={(row) => row.id}
                      empty="No sessions yet."
                    />
                  </Card>
                </Reveal>
              </>
            )}

            <Reveal>
              <Card
                title="Areas and topics"
                subtitle="Areas are domains; topics are what you sit down and study"
                icon={FolderTree}
                accent="learning"
                // Only "Topic" here: the page header already carries "New area",
                // and two buttons squeezed the card title into "Areas and t..."
                // at phone width.
                action={
                  <Button size="sm" variant="ghost" icon={Plus}
                          onClick={() => setEditingTopic(null)}>
                    Topic
                  </Button>
                }
              >
                {(areas.data?.areas.length ?? 0) === 0
                  && (topics.data?.topics.length ?? 0) === 0 ? (
                  <p className="text-label text-ink-subtle">
                    Nothing organised yet. You can log sessions without a topic —
                    they count as Unfiled — but grouping them is what makes the
                    distribution above useful.
                  </p>
                ) : (
                  <div className="flex flex-col gap-4">
                    {areas.data?.areas.map((area) => (
                      <div key={area.id}>
                        <div className="mb-2 flex min-w-0 items-center gap-2">
                          <span className={cn('shrink-0 text-label',
                            accentText[toAccent(area.accent)])}>
                            ●
                          </span>
                          <span className="truncate text-label text-ink">{area.name}</span>
                          <span className="truncate text-meta text-ink-subtle">
                            {hoursMinutes(area.total_minutes)}
                            {area.weekly_target_minutes
                              ? ` · ${hoursMinutes(area.weekly_target_minutes)}/wk target`
                              : ''}
                          </span>
                          <span className="ml-auto flex shrink-0 gap-1">
                            <Button size="sm" variant="ghost" icon={Pencil}
                                    aria-label={`Edit ${area.name}`}
                                    onClick={() => setEditingArea(area)} />
                            <Button size="sm" variant="ghost" icon={Trash2}
                                    aria-label={`Archive ${area.name}`}
                                    onClick={() => removeArea.mutate(area.id)} />
                          </span>
                        </div>

                        <div className="grid gap-2 sm:grid-cols-2">
                          {topics.data?.topics
                            .filter((topic) => topic.area_id === area.id)
                            .map((topic) => (
                              <TopicRow
                                key={topic.id} topic={topic}
                                onStudy={() => setLogging(topic.id)}
                                onEdit={() => setEditingTopic(topic)}
                                onRemove={() => removeTopic.mutate(topic.id)}
                              />
                            ))}
                        </div>
                      </div>
                    ))}

                    {(topics.data?.topics.filter((t) => !t.area_id).length ?? 0) > 0 && (
                      <div>
                        <p className="mb-2 text-label text-ink-muted">Unfiled</p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {topics.data?.topics.filter((t) => !t.area_id).map((topic) => (
                            <TopicRow
                              key={topic.id} topic={topic}
                              onStudy={() => setLogging(topic.id)}
                              onEdit={() => setEditingTopic(topic)}
                              onRemove={() => removeTopic.mutate(topic.id)}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </Card>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>

      {/* Keyed and conditionally mounted so each editor seeds from whichever row
          you opened - one long-lived instance would keep the first row's values. */}
      {logging !== undefined && (
        <SessionLogger
          key={logging ?? 'new'}
          open
          topicId={logging}
          topics={topics.data?.topics ?? []}
          onClose={() => setLogging(undefined)}
        />
      )}

      {editingArea !== undefined && (
        <AreaEditor
          key={editingArea?.id ?? 'new'}
          open
          area={editingArea}
          onClose={() => setEditingArea(undefined)}
        />
      )}

      {editingTopic !== undefined && (
        <TopicEditor
          key={editingTopic?.id ?? 'new'}
          open
          topic={editingTopic}
          areas={areas.data?.areas ?? []}
          onClose={() => setEditingTopic(undefined)}
        />
      )}
    </>
  )
}

function TopicRow({
  topic, onStudy, onEdit, onRemove,
}: {
  topic: LearningTopic
  onStudy: () => void
  onEdit: () => void
  onRemove: () => void
}) {
  return (
    // min-w-0 because a grid item defaults to min-width:auto, so without it this
    // row refuses to shrink below its three buttons plus the topic name and
    // pushes the whole page into horizontal scroll on a phone.
    <div className="flex min-w-0 items-center gap-2 rounded-md border border-line bg-surface-base px-3 py-2">
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-label text-ink">{topic.name}</span>
          {topic.status !== 'active' && (
            <Badge tone={topic.status === 'done' ? 'success' : 'neutral'}>
              {topic.status}
            </Badge>
          )}
        </span>
        <span className="block truncate text-meta text-ink-subtle">
          {hoursMinutes(topic.total_minutes)} · {topic.session_count ?? 0} session
          {topic.session_count === 1 ? '' : 's'}
          {topic.last_studied && ` · last ${topic.last_studied}`}
        </span>
      </span>
      <Button size="sm" variant="ghost" icon={Pencil} className="shrink-0"
              aria-label={`Edit ${topic.name}`} onClick={onEdit} />
      <Button size="sm" variant="ghost" icon={Trash2} className="shrink-0"
              aria-label={`Archive ${topic.name}`} onClick={onRemove} />
      <Button size="sm" variant="secondary" className="shrink-0" onClick={onStudy}>
        Study
      </Button>
    </div>
  )
}
