import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import {
  BedDouble, Droplets, Footprints, Info, NotebookPen, Smile, Sun, Timer,
} from 'lucide-react'

import type { LifestyleDay, LifestyleSummary } from '../api/types'
import {
  useLifestyleDay, useLifestyleSummary, useLogSleep, useSaveLifestyle,
} from '../api/queries'
import { TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { BookWorkspace } from '../components/ui/BookPreview'
import { WorkspaceStory } from '../components/ui/WorkspaceStory'
import { cn } from '../lib/cn'
import { shortDate, todayISO } from '../lib/date'
import { spring } from '../lib/motion'

function hoursMinutes(minutes: number | null | undefined) {
  if (!minutes) return '—'
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}

/** Quick increments, because nobody types "1750" four times a day. */
const WATER_STEPS = [250, 500]

function WaterTracker({
  value, target, onChange, busy,
}: {
  value: number
  target: number
  onChange: (next: number) => void
  busy?: boolean
}) {
  const pct = target > 0 ? Math.min(100, (value / target) * 100) : 0
  const glasses = Math.round(target / 250)
  const filled = Math.round(value / 250)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <span className="tabular text-metric text-ink">{value}</span>
        <span className="text-label text-ink-muted">/ {target} ml</span>
      </div>

      <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
        <m.div
          className="h-full rounded-full bg-recovery"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={spring.soft}
        />
      </div>

      {/* A row of glasses reads faster than a number when you are checking
          whether to go and fill one up. */}
      <div className="flex flex-wrap gap-1" aria-hidden>
        {Array.from({ length: Math.min(glasses, 16) }, (_, index) => (
          <span
            key={index}
            className={cn(
              'h-6 w-4 rounded-sm border transition-colors',
              index < filled
                ? 'border-recovery bg-recovery/40'
                : 'border-line bg-surface-raised',
            )}
          />
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {WATER_STEPS.map((step) => (
          <Button
            key={step} size="sm" variant="secondary" disabled={busy}
            onClick={() => onChange(value + step)}
          >
            +{step} ml
          </Button>
        ))}
        {value > 0 && (
          <Button size="sm" variant="ghost" disabled={busy}
                  onClick={() => onChange(Math.max(0, value - 250))}>
            −250 ml
          </Button>
        )}
      </div>
    </div>
  )
}

function Scale1to5({
  label, value, onChange, lowLabel, highLabel,
}: {
  label: string
  value: number | null
  onChange: (next: number) => void
  lowLabel: string
  highLabel: string
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="text-caption text-ink-subtle">{lowLabel} → {highLabel}</span>
      </div>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            aria-pressed={value === option}
            aria-label={`${label}: ${option} of 5`}
            className={cn(
              'flex h-9 flex-1 items-center justify-center rounded-md border tabular text-label transition-colors',
              value === option
                ? 'border-lifestyle bg-lifestyle/15 text-lifestyle'
                : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  )
}

function SleepForm({ date }: { date: string }) {
  const day = useLifestyleDay(date)
  const log = useLogSleep()

  const stored = day.data?.sleep
  const [bedtime, setBedtime] = useState(stored?.bedtime ?? '23:00')
  const [wake, setWake] = useState(stored?.wake_time ?? '07:00')
  const [quality, setQuality] = useState<number | null>(stored?.quality ?? null)

  // Mirrors the server's calculation so the duration updates as you type rather
  // than only after a save round-trip.
  const duration = useMemo(() => {
    const toMinutes = (value: string) => {
      const [h, m] = value.split(':').map(Number)
      return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null
    }
    const start = toMinutes(bedtime)
    const end = toMinutes(wake)
    if (start == null || end == null) return null
    return ((end - start) % 1440 + 1440) % 1440 || null
  }, [bedtime, wake])

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Asleep at</span>
          <input
            type="time" value={bedtime}
            onChange={(event) => setBedtime(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Awake at</span>
          <input
            type="time" value={wake}
            onChange={(event) => setWake(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
        </label>
      </div>

      <p className="tabular text-section text-ink">{hoursMinutes(duration)}</p>

      <Scale1to5
        label="Quality" value={quality} onChange={setQuality}
        lowLabel="broken" highLabel="deep"
      />
      <p className="flex items-start gap-1.5 text-caption text-ink-subtle">
        <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
        Quality is recorded for your own reference and never scored — it is a
        feeling, and an app that scored it would be paying you to report sleeping
        well.
      </p>

      <Button
        variant="primary" loading={log.isPending} disabled={!duration}
        onClick={() => log.mutate({
          date, bedtime, wake_time: wake, quality: quality ?? undefined,
        })}
        className="self-start"
      >
        Save night
      </Button>
    </div>
  )
}

function MoodChart({ days }: { days: LifestyleDay[] }) {
  const points = days
    .filter((day) => day.mood != null)
    .map((day) => ({ label: shortDate(day.date), value: day.mood as number }))

  if (points.length < 2) {
    return (
      <p className="text-label text-ink-subtle">
        Log how you feel for a few days and the pattern shows up here.
      </p>
    )
  }
  return (
    <TrendChart
      data={points} accent="lifestyle" height={180} name="Mood" domain={[0, 5]}
    />
  )
}

export function Lifestyle() {
  const [date] = useState(todayISO)
  const summary = useLifestyleSummary()
  const day = useLifestyleDay(date)
  const save = useSaveLifestyle(date)

  const current = day.data?.lifestyle
  const targets = day.data?.targets

  function patch(changes: Partial<LifestyleDay>) {
    save.mutate(changes)
  }

  return (
    <>
      <PageHeader
        title="Lifestyle"
        description="Sleep feeds Recovery, a steady schedule feeds Discipline, and steps feed Stamina."
        icon={Sun}
        accent="recovery"
      />

      <QueryBoundary query={summary} loading={<SkeletonGrid />}>
        {(data: LifestyleSummary) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal><WorkspaceStory kind="lifestyle" /></Reveal>
            <BookWorkspace kind="journal">
            <Reveal className="grid grid-cols-2 gap-3">
              <StatCard
                label="Average sleep"
                value={hoursMinutes(data.averages.sleep_minutes)}
                icon={BedDouble} accent="recovery"
                hint={`target ${hoursMinutes(data.targets.sleep_minutes)}`}
              />
              <StatCard
                label="Schedule"
                value={data.averages.schedule_consistency != null
                  ? `${data.averages.schedule_consistency}%`
                  : '—'}
                icon={Timer} accent="discipline" hint="bed/wake consistency"
              />
              <StatCard
                label="Average water"
                value={data.averages.water_ml ? `${data.averages.water_ml} ml` : '—'}
                icon={Droplets} accent="recovery"
                hint={`target ${data.targets.water_ml} ml`}
              />
              <StatCard
                label="Average steps"
                value={data.averages.steps?.toLocaleString() ?? '—'}
                icon={Footprints} accent="lifestyle"
                hint={`target ${data.targets.steps.toLocaleString()}`}
              />
            </Reveal>

            </BookWorkspace>

            <Reveal className="grid gap-4 lg:grid-cols-2">
              <Card title="Last night" icon={BedDouble} accent="recovery">
                <SleepForm date={date} />
              </Card>

              <Card title="Water" icon={Droplets} accent="recovery">
                <WaterTracker
                  value={current?.water_ml ?? 0}
                  target={targets?.water_ml ?? 2500}
                  onChange={(next) => patch({ water_ml: next })}
                  busy={save.isPending}
                />
              </Card>
            </Reveal>

            <Reveal className="grid gap-4 lg:grid-cols-2">
              <Card title="Movement and light" icon={Footprints} accent="lifestyle">
                <div className="flex flex-col gap-3">
                  <label className="flex flex-col gap-1">
                    <span className="text-meta text-ink-muted">
                      Steps today (target {targets?.steps.toLocaleString() ?? '8,000'})
                    </span>
                    <input
                      type="number" min="0" inputMode="numeric"
                      defaultValue={current?.steps ?? ''}
                      onBlur={(event) => patch({
                        steps: event.target.value === '' ? null : Number(event.target.value),
                      })}
                      className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-meta text-ink-muted">
                      Time outside (minutes)
                    </span>
                    <input
                      type="number" min="0" inputMode="numeric"
                      defaultValue={current?.sunlight_minutes ?? ''}
                      onBlur={(event) => patch({
                        sunlight_minutes: event.target.value === ''
                          ? null : Number(event.target.value),
                      })}
                      className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
                    />
                  </label>
                  <p className="text-caption text-ink-subtle">
                    Steps blend with logged cardio to feed Stamina. Time outside is
                    tracked but not scored.
                  </p>
                </div>
              </Card>

              <Card title="How you feel" icon={Smile} accent="lifestyle">
                <div className="flex flex-col gap-3">
                  <Scale1to5
                    label="Mood" value={current?.mood ?? null}
                    onChange={(value) => patch({ mood: value })}
                    lowLabel="low" highLabel="great"
                  />
                  <Scale1to5
                    label="Stress" value={current?.stress ?? null}
                    onChange={(value) => patch({ stress: value })}
                    lowLabel="calm" highLabel="frayed"
                  />
                  <Scale1to5
                    label="Energy" value={current?.energy ?? null}
                    onChange={(value) => patch({ energy: value })}
                    lowLabel="drained" highLabel="sharp"
                  />
                  <div className="flex items-start gap-1.5">
                    <Badge tone="neutral" className="shrink-0 whitespace-nowrap">not scored</Badge>
                    <p className="text-caption text-ink-subtle">
                      These are feelings, not behaviour. They are charted so you can
                      see what correlates with what — scoring them would just pay
                      you to report feeling good.
                    </p>
                  </div>
                </div>
              </Card>
            </Reveal>

            <Reveal className="grid gap-4 lg:grid-cols-2">
              <Card title="Sleep, recent nights" icon={BedDouble} accent="recovery">
                {data.sleep.length < 2 ? (
                  <p className="text-label text-ink-subtle">
                    Log a few nights and the trend shows up here.
                  </p>
                ) : (
                  <TrendChart
                    data={data.sleep.map((night) => ({
                      label: shortDate(night.date),
                      value: Math.round((night.duration_minutes / 60) * 10) / 10,
                    }))}
                    accent="recovery" height={180} unit="h" name="Sleep"
                  />
                )}
              </Card>

              <Card title="Mood over time" icon={Smile} accent="lifestyle">
                <MoodChart days={data.lifestyle} />
              </Card>
            </Reveal>

            <Reveal>
              <Card title="Journal" icon={NotebookPen} accent="goals">
                <p className="whitespace-pre-wrap font-serif text-label leading-7 text-ink-muted">{current?.journal || 'Your day is still an open page.'}</p>
                <p className="mt-2 text-caption text-ink-subtle">
                  Open the journal cover above to write, revisit a day, or ask for an AI draft.
                </p>
              </Card>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>
    </>
  )
}
