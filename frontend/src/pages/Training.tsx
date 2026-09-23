import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { m } from 'motion/react'
import {
  Activity, CalendarDays, Dumbbell, Flame, ListChecks, Pencil, Play, Plus,
  Ruler, Trash2, Trophy, Weight,
} from 'lucide-react'

import type { Routine, TrainingSummary, Workout } from '../api/types'
import {
  useDeleteRoutine, useDeleteWorkout, useLogMeasurement, useRoutines,
  useStartWorkout, useTrainingSummary,
} from '../api/queries'
import { RoutineEditor } from '../components/training/RoutineEditor'
import { TrendChart } from '../components/charts'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmationDialog } from '../components/ui/ConfirmationDialog'
import { DataTable, type Column } from '../components/ui/DataTable'
import { EmptyState } from '../components/ui/EmptyState'
import { Modal } from '../components/ui/Modal'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { BookWorkspace } from '../components/ui/BookPreview'
import { WorkspaceStory } from '../components/ui/WorkspaceStory'
import { shortDate, todayISO } from '../lib/date'
import { spring } from '../lib/motion'

const METRICS = [
  { metric: 'weight', label: 'Body weight', unit: 'kg' },
  { metric: 'body_fat', label: 'Body fat', unit: '%' },
  { metric: 'waist', label: 'Waist', unit: 'cm' },
  { metric: 'chest', label: 'Chest', unit: 'cm' },
  { metric: 'arm', label: 'Arm', unit: 'cm' },
  { metric: 'thigh', label: 'Thigh', unit: 'cm' },
]


/**
 * Balance is measured in working sets, not volume - a set of calf raises and a
 * set of squats are comparable as training stimulus in a way their kilogram
 * totals are not. The API orders by volume, so this re-sorts to match the bars
 * it actually draws. Lengths are relative to the biggest group; there is no
 * "correct" absolute number of sets to scale against.
 */
function MuscleBalance({ rows }: { rows: TrainingSummary['by_muscle'] }) {
  const ordered = [...rows].sort((a, b) => b.sets - a.sets)
  const max = Math.max(...ordered.map((row) => row.sets), 1)

  return (
    <div className="flex flex-col gap-2">
      {ordered.map((row, index) => (
        <div key={row.muscle} className="flex items-center gap-3">
          <span className="w-20 shrink-0 truncate text-meta capitalize text-ink-muted">
            {row.muscle.replace('-', ' ')}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
            <m.div
              className="h-full rounded-full bg-fitness"
              initial={{ width: 0 }}
              animate={{ width: `${(row.sets / max) * 100}%` }}
              transition={{ ...spring.soft, delay: index * 0.04 }}
            />
          </div>
          <span className="tabular w-10 shrink-0 text-right text-meta text-ink-subtle">
            {row.sets}
          </span>
        </div>
      ))}
    </div>
  )
}

function MeasurementForm({ open, onClose }: { open: boolean; onClose: () => void }) {
  const log = useLogMeasurement()
  const [metric, setMetric] = useState(METRICS[0].metric)
  const [value, setValue] = useState('')
  const [date, setDate] = useState(todayISO)

  const unit = METRICS.find((option) => option.metric === metric)?.unit

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (value === '') return
    log.mutate(
      { metric, date, value: Number(value), unit },
      { onSuccess: () => { setValue(''); onClose() } },
    )
  }

  return (
    <Modal open={open} onClose={onClose} title="Log a measurement">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Metric</span>
          <select
            value={metric}
            onChange={(event) => setMetric(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          >
            {METRICS.map((option) => (
              <option key={option.metric} value={option.metric}>{option.label}</option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Value ({unit})</span>
          <input
            type="number" step="0.1" min="0" value={value} required
            onChange={(event) => setValue(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Date</span>
          <input
            type="date" value={date} max={todayISO()}
            onChange={(event) => setDate(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={log.isPending}>Save</Button>
        </div>
      </form>
    </Modal>
  )
}

export function Training() {
  const navigate = useNavigate()
  const query = useTrainingSummary()
  const start = useStartWorkout()
  const remove = useDeleteWorkout()

  const routines = useRoutines()
  const removeRoutine = useDeleteRoutine()

  const [measuring, setMeasuring] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<Workout | null>(null)
  /** undefined = closed, null = creating, a routine = editing that one. */
  const [editing, setEditing] = useState<Routine | null | undefined>(undefined)

  const trend = useMemo(
    () => (query.data?.volume_trend ?? []).map((point) => ({
      label: shortDate(point.date),
      value: Math.round(point.volume),
    })),
    [query.data],
  )

  // The endpoint returns the last 20 rows date-descending, which repeats a
  // metric once per time you weighed yourself. Only the newest of each is a
  // current fact about you.
  const latestMeasurements = useMemo(() => {
    const newest = new Map<string, TrainingSummary['measurements'][number]>()
    for (const entry of query.data?.measurements ?? []) {
      if (!newest.has(entry.metric)) newest.set(entry.metric, entry)
    }
    return [...newest.values()]
  }, [query.data])

  function beginWorkout(routineId?: number) {
    start.mutate(
      routineId ? { date: todayISO(), routine_id: routineId } : { date: todayISO(), name: 'Workout' },
      { onSuccess: (workout) => navigate(`/training/${workout.id}`) },
    )
  }

  const sessionColumns: Column<Workout>[] = [
    {
      key: 'date',
      header: 'Date',
      render: (row) => <span className="tabular text-ink">{row.date}</span>,
    },
    {
      key: 'name',
      header: 'Session',
      render: (row) => row.name ?? 'Workout',
    },
    {
      key: 'sets',
      header: 'Sets',
      align: 'right',
      render: (row) => <span className="tabular">{row.total_sets}</span>,
    },
    {
      key: 'volume',
      header: 'Volume',
      align: 'right',
      hideBelow: 'sm',
      render: (row) => (
        <span className="tabular">{Math.round(row.total_volume).toLocaleString()}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (row) => (
        <div className="flex justify-end gap-1">
          <Button size="sm" variant="ghost" onClick={() => navigate(`/training/${row.id}`)}>
            Open
          </Button>
          <Button size="sm" variant="danger" onClick={() => setPendingDelete(row)}>
            Delete
          </Button>
        </div>
      ),
    },
  ]

  const recordColumns: Column<TrainingSummary['records'][number]>[] = [
    { key: 'exercise', header: 'Exercise', render: (row) => row.exercise },
    {
      key: 'best',
      header: 'Best set',
      align: 'right',
      render: (row) => (
        <span className="tabular text-ink">
          {row.weight}{row.weight_unit} × {row.reps}
        </span>
      ),
    },
    {
      key: 'date',
      header: 'Set on',
      align: 'right',
      hideBelow: 'sm',
      render: (row) => <span className="tabular text-ink-subtle">{row.date}</span>,
    },
  ]

  return (
    <>
      <PageHeader
        title="Training"
        description={
          query.data?.recent[0]
            ? `Last session ${query.data.recent[0].date}. Every set you log here feeds Strength, Stamina and Agility.`
            : 'Every set you log here feeds Strength, Stamina and Agility.'
        }
        icon={Dumbbell}
        accent="fitness"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/training/library">
              <Button size="sm" icon={Dumbbell}>
                Exercises
              </Button>
            </Link>
            <Button size="sm" icon={Ruler} onClick={() => setMeasuring(true)}>
              Measure
            </Button>
            <Button size="sm" icon={ListChecks} onClick={() => setEditing(null)}>
              New routine
            </Button>
            <Button
              size="sm" variant="primary" icon={Plus}
              onClick={() => beginWorkout()} loading={start.isPending}
            >
              Start workout
            </Button>
          </div>
        }
      />

      <QueryBoundary query={query} loading={<SkeletonGrid />}>
        {(summary) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal><WorkspaceStory kind="training" /></Reveal>
            <BookWorkspace kind="exercise">
            <Reveal className="grid grid-cols-2 gap-3">
              <StatCard
                label="Sessions" value={summary.total_sessions}
                icon={CalendarDays} accent="fitness"
              />
              <StatCard
                label="Total volume"
                value={Math.round(summary.total_volume).toLocaleString()}
                icon={Weight} accent="fitness" hint="warm-ups excluded"
              />
              <StatCard
                label="Avg per session"
                value={
                  summary.total_sessions
                    ? Math.round(summary.total_volume / summary.total_sessions).toLocaleString()
                    : '—'
                }
                icon={Flame} accent="discipline" hint="kg × reps"
              />
              <StatCard
                label="Records" value={summary.records.length}
                icon={Trophy} accent="goals" hint="exercises tracked"
              />
            </Reveal>

            </BookWorkspace>

            {summary.total_sessions === 0 ? (
              <Reveal>
                <EmptyState
                  icon={Dumbbell}
                  title="No sessions yet"
                  description="Start a workout and log your first set. Strength stays unobserved until there is something real to measure."
                  action={
                    <Button variant="primary" icon={Plus} onClick={() => beginWorkout()}>
                      Start workout
                    </Button>
                  }
                />
              </Reveal>
            ) : (
              <>
                <Reveal>
                  <Card
                    title="Volume trend" subtitle="Per training day, warm-ups excluded"
                    icon={Activity} accent="fitness"
                  >
                    <TrendChart data={trend} accent="fitness" unit=" kg" name="Volume" />
                  </Card>
                </Reveal>

                <Reveal className="grid gap-4 lg:grid-cols-2">
                  <Card
                    title="Muscle balance" subtitle="Working sets, last 30 days"
                    icon={Dumbbell} accent="fitness"
                  >
                    {summary.by_muscle.length === 0 ? (
                      <p className="text-label text-ink-subtle">Nothing logged yet.</p>
                    ) : (
                      <MuscleBalance rows={summary.by_muscle} />
                    )}
                  </Card>

                  <Card title="Personal records" icon={Trophy} accent="goals">
                    <DataTable
                      columns={recordColumns}
                      rows={summary.records}
                      rowKey={(row) => row.exercise_id}
                      empty="No records yet — log a working set to set one."
                    />
                  </Card>
                </Reveal>

                <Reveal>
                  <Card title="Recent sessions" icon={CalendarDays} accent="fitness">
                    <DataTable
                      columns={sessionColumns}
                      rows={summary.recent}
                      rowKey={(row) => row.id}
                      empty="No sessions yet."
                    />
                  </Card>
                </Reveal>
              </>
            )}

            <Reveal>
              <Card
                title="Routines"
                subtitle="Plans you can start a session from"
                icon={ListChecks}
                accent="fitness"
                action={
                  <Button size="sm" variant="ghost" icon={Plus} onClick={() => setEditing(null)}>
                    New
                  </Button>
                }
              >
                {(routines.data?.routines.length ?? 0) === 0 ? (
                  <p className="text-label text-ink-subtle">
                    No routines yet. Build one and starting a session pre-fills the
                    exercises — you still log what you actually lift.
                  </p>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {routines.data?.routines.map((routine) => (
                      // min-w-0: this row is a grid item, so it defaults to
                      // min-width:auto and refuses to shrink below the width of
                      // its three action buttons plus the routine name - which
                      // scrolled the whole page sideways on a phone.
                      <div
                        key={routine.id}
                        className="flex min-w-0 items-center gap-2 rounded-md border border-line bg-surface-base px-3 py-2"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-label text-ink">
                            {routine.name}
                          </span>
                          <span className="block truncate text-meta text-ink-subtle">
                            {routine.exercises.length} exercise
                            {routine.exercises.length === 1 ? '' : 's'}
                            {routine.split_type && routine.split_type !== 'custom'
                              && ` · ${routine.split_type.replace(/-/g, ' ')}`}
                          </span>
                        </span>
                        <Button
                          size="sm" variant="ghost" icon={Pencil}
                          aria-label={`Edit ${routine.name}`}
                          onClick={() => setEditing(routine)}
                        />
                        <Button
                          size="sm" variant="ghost" icon={Trash2}
                          aria-label={`Delete ${routine.name}`}
                          onClick={() => removeRoutine.mutate(routine.id)}
                        />
                        <Button
                          size="sm" variant="primary" icon={Play}
                          onClick={() => beginWorkout(routine.id)}
                          loading={start.isPending}
                        >
                          Start
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </Reveal>

            <Reveal>
              <Card
                title="Body measurements"
                subtitle="Context for the numbers above — not scored"
                icon={Ruler}
                accent="recovery"
                action={
                  <Button size="sm" variant="ghost" icon={Plus} onClick={() => setMeasuring(true)}>
                    Log
                  </Button>
                }
              >
                {latestMeasurements.length === 0 ? (
                  <p className="text-label text-ink-subtle">
                    Nothing recorded yet. Body weight is the useful one to start with.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {latestMeasurements.map((entry) => (
                      <Badge key={entry.metric} tone="neutral">
                        <span className="capitalize">{entry.metric.replace('_', ' ')}</span>
                        {' '}
                        <span className="tabular text-ink">
                          {entry.value}{entry.unit ?? ''}
                        </span>
                        <span className="tabular text-ink-subtle"> · {entry.date}</span>
                      </Badge>
                    ))}
                  </div>
                )}
              </Card>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>

      <MeasurementForm open={measuring} onClose={() => setMeasuring(false)} />

      {/*
        Keyed and conditionally mounted so the editor's form state is seeded from
        whichever routine you opened. A single long-lived instance would keep the
        first routine's exercises when you opened the second.
      */}
      {editing !== undefined && (
        <RoutineEditor
          key={editing?.id ?? 'new'}
          open
          routine={editing}
          onClose={() => setEditing(undefined)}
        />
      )}

      <ConfirmationDialog
        open={pendingDelete !== null}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) remove.mutate(pendingDelete.id)
          setPendingDelete(null)
        }}
        title="Delete this session?"
        description={
          pendingDelete
            ? `${pendingDelete.date} — ${pendingDelete.total_sets} sets. Strength, Stamina and Agility will be recalculated without it.`
            : ''
        }
        confirmLabel="Delete"
        destructive
        busy={remove.isPending}
      />
    </>
  )
}
