import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { m } from 'motion/react'
import { Check, Dumbbell, Plus, Timer, Trash2, TrendingUp } from 'lucide-react'

import type { Exercise, LoggedSet, Workout } from '../api/types'
import {
  useExerciseHistory, useProfile, useRoutine, useSaveWorkout, useWorkout,
} from '../api/queries'
import { ExercisePicker } from '../components/training/ExercisePicker'
import { RestTimer } from '../components/training/RestTimer'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { slideIn, spring } from '../lib/motion'
import { asUnit, toKg, type WeightUnit } from '../lib/units'

/** A set as the form holds it - strings, because a half-typed "8" is not a number. */
interface DraftSet {
  key: string
  exercise_id: number
  exercise_name: string
  category: string
  weight: string
  /**
   * Per set, because that is how the column stores it and how a gym works: a
   * barbell in kilograms and a machine stack in pounds is an ordinary session,
   * not an edge case. The toggle sets a whole exercise at once.
   */
  weight_unit: WeightUnit
  reps: string
  duration: string
  is_warmup: boolean
}

let keyCounter = 0
const nextKey = () => `set-${++keyCounter}`

function toDraft(set: LoggedSet): DraftSet {
  return {
    key: nextKey(),
    exercise_id: set.exercise_id,
    exercise_name: set.exercise_name ?? 'Exercise',
    category: set.category ?? 'strength',
    weight: set.weight != null ? String(set.weight) : '',
    // A stored set keeps the unit it was lifted in. Re-opening a session must
    // never reinterpret last month's numbers through today's preference.
    weight_unit: asUnit(set.weight_unit),
    reps: set.reps != null ? String(set.reps) : '',
    duration: set.duration_seconds != null ? String(Math.round(set.duration_seconds / 60)) : '',
    is_warmup: Boolean(set.is_warmup),
  }
}

/**
 * A row you have not typed into is not a set.
 *
 * Routine-seeded sessions open with a row per planned set, so without this the
 * header would claim 11 working sets before you had lifted anything, and
 * finishing would persist the blanks as real logged sets.
 */
function hasData(draft: DraftSet): boolean {
  return draft.weight !== '' || draft.reps !== '' || draft.duration !== ''
}

function toPayload(draft: DraftSet): LoggedSet {
  const minutes = Number(draft.duration)
  return {
    exercise_id: draft.exercise_id,
    weight: draft.weight === '' ? null : Number(draft.weight),
    weight_unit: draft.weight_unit,
    reps: draft.reps === '' ? null : Number(draft.reps),
    duration_seconds: draft.duration === '' ? null : Math.round(minutes * 60),
    is_warmup: draft.is_warmup,
  }
}

function PreviousPerformance(
  { exerciseId, excludeSession }: { exerciseId: number; excludeSession: number },
) {
  const { data } = useExerciseHistory(exerciseId, excludeSession)
  if (!data) return null

  const last = data.last_session_sets
  if (last.length === 0) {
    return <span className="text-meta text-ink-subtle">First time logging this</span>
  }

  // "Last time: 135x8" is a different instruction depending on the unit, so the
  // unit is shown - once at the end when the session used one, and per set on
  // the rare day that mixed them.
  const units = new Set(last.filter((set) => set.weight != null)
    .map((set) => asUnit(set.weight_unit)))
  const mixed = units.size > 1
  const summary = last
    .map((set) => (set.weight != null
      ? `${set.weight}${mixed ? asUnit(set.weight_unit) : ''}×${set.reps ?? '?'}`
      : `${set.reps ?? '?'} reps`))
    .join(', ')
  const suffix = units.size === 1 ? ` ${[...units][0]}` : ''

  return (
    <span className="text-meta text-ink-subtle">
      Last time: <span className="text-ink-muted">{summary}{suffix}</span>
      {data.heaviest_set && (
        <>
          {' · '}best {data.heaviest_set.weight}
          {data.heaviest_set.weight_unit}×{data.heaviest_set.reps}
        </>
      )}
    </span>
  )
}

interface ExerciseBlockProps {
  exerciseId: number
  workoutId: number
  name: string
  sets: DraftSet[]
  onChange: (key: string, patch: Partial<DraftSet>) => void
  onRemove: (key: string) => void
  onAddSet: (exerciseId: number, name: string, category: string) => void
  onUnit: (exerciseId: number, unit: WeightUnit) => void
  onRest: () => void
}

function ExerciseBlock({
  exerciseId, workoutId, name, sets, onChange, onRemove, onAddSet, onUnit, onRest,
}: ExerciseBlockProps) {
  const isCardio = sets[0]?.category !== 'strength'
  const unit = sets[0]?.weight_unit ?? 'kg'

  return (
    <Card
      title={name}
      subtitle={<PreviousPerformance exerciseId={exerciseId} excludeSession={workoutId} />}
      icon={Dumbbell}
      accent="fitness"
      action={
        <Button size="sm" variant="ghost" icon={Timer} onClick={onRest} aria-label="Rest timer" />
      }
    >
      <div className="flex max-w-md flex-col gap-2">
        <div className="grid grid-cols-[2rem_minmax(0,1fr)_minmax(0,1fr)_2.5rem_2rem] items-center gap-2 text-caption uppercase tracking-wide text-ink-subtle">
          <span className="text-center">Set</span>
          {isCardio ? (
            <span>Minutes</span>
          ) : (
            /* The toggle is the column header, because that is where you are
               already looking when you wonder what the number means. Per
               exercise: the barbell and the machine stack can disagree. */
            <span className="flex items-center gap-1.5">
              Weight
              <span className="flex overflow-hidden rounded-pill border border-line">
                {(['kg', 'lb'] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => onUnit(exerciseId, option)}
                    aria-pressed={unit === option}
                    aria-label={`Record ${name} in ${option === 'kg' ? 'kilograms' : 'pounds'}`}
                    className={cn(
                      'px-2 py-0.5 text-meta lowercase tracking-normal transition-colors',
                      unit === option
                        ? 'bg-fitness/20 text-fitness'
                        : 'text-ink-subtle hover:text-ink',
                    )}
                  >
                    {option}
                  </button>
                ))}
              </span>
            </span>
          )}
          <span>{isCardio ? '' : 'Reps'}</span>
          <span className="text-center">W/U</span>
          <span />
        </div>

        {sets.map((set, index) => (
          <m.div
            key={set.key}
            layout
            className="grid grid-cols-[2rem_minmax(0,1fr)_minmax(0,1fr)_2.5rem_2rem] items-center gap-2"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={spring.snappy}
          >
            <span
              className={cn('tabular text-center text-meta',
                set.is_warmup ? 'text-ink-subtle' : 'text-ink-muted')}
            >
              {set.is_warmup ? '–' : sets.slice(0, index + 1).filter((s) => !s.is_warmup).length}
            </span>

            {isCardio ? (
              <input
                type="number" inputMode="decimal" min="0" value={set.duration}
                onChange={(event) => onChange(set.key, { duration: event.target.value })}
                placeholder="min" aria-label="Minutes"
                className="col-span-2 rounded-md border border-line bg-surface-base px-2 py-1.5 text-label tabular text-ink outline-none focus:border-brand"
              />
            ) : (
              <>
                <input
                  type="number" inputMode="decimal" step="0.5" min="0" value={set.weight}
                  onChange={(event) => onChange(set.key, { weight: event.target.value })}
                  placeholder={unit} aria-label={`Weight in ${unit}`}
                  className="rounded-md border border-line bg-surface-base px-2 py-1.5 text-label tabular text-ink outline-none focus:border-brand"
                />
                <input
                  type="number" inputMode="numeric" min="0" value={set.reps}
                  onChange={(event) => onChange(set.key, { reps: event.target.value })}
                  placeholder="reps" aria-label="Reps"
                  className="rounded-md border border-line bg-surface-base px-2 py-1.5 text-label tabular text-ink outline-none focus:border-brand"
                />
              </>
            )}

            <button
              type="button"
              onClick={() => onChange(set.key, { is_warmup: !set.is_warmup })}
              aria-pressed={set.is_warmup}
              aria-label="Mark as warm-up"
              title="Warm-up sets are excluded from volume and records"
              className={cn(
                'mx-auto flex size-6 items-center justify-center rounded border text-caption transition-colors',
                set.is_warmup
                  ? 'border-warning bg-warning/15 text-warning'
                  : 'border-line text-ink-subtle hover:border-line-strong',
              )}
            >
              {set.is_warmup ? <Check size={12} /> : ''}
            </button>

            <button
              type="button"
              onClick={() => onRemove(set.key)}
              aria-label="Remove set"
              className="text-ink-subtle transition-colors hover:text-danger"
            >
              <Trash2 size={14} />
            </button>
          </m.div>
        ))}

        <Button
          size="sm" variant="ghost" icon={Plus}
          onClick={() => onAddSet(exerciseId, name, sets[0]?.category ?? 'strength')}
          className="self-start"
        >
          Add set
        </Button>
      </div>
    </Card>
  )
}

export function WorkoutSession() {
  const { workoutId } = useParams()
  const navigate = useNavigate()
  const id = Number(workoutId)

  const query = useWorkout(id)
  const save = useSaveWorkout(id)

  const [drafts, setDrafts] = useState<DraftSet[] | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [restOpen, setRestOpen] = useState(false)

  // Server sets seed the form once; after that local edits own it. Same reasoning
  // as Today - copying into state via an effect would clobber an in-flight edit
  // whenever the query refetched. Memoised because toDraft mints a fresh key per
  // call: remapping on every render would remount the inputs and drop focus.
  // A session started from a routine has no sets yet, so its plan seeds the form:
  // the exercises appear with empty inputs, ready to type into. The plan is never
  // persisted - only what you actually lift is saved, and so only that is scored.
  const plan = useRoutine(
    query.data && query.data.sets.length === 0 ? query.data.routine_id : null,
  )

  // Your default, not the app's. Somebody who lifts in pounds should not pick
  // the unit on every set forever - and eventually forget once, and record a
  // 225 kg bench press.
  const profile = useProfile()
  const preferred = asUnit(profile.data?.profile.weight_unit)

  const sets = useMemo(() => {
    if (drafts) return drafts
    if (!query.data) return []
    if (query.data.sets.length > 0) return query.data.sets.map(toDraft)
    // Stored sets carry their own unit; planned rows have to borrow yours, so
    // they wait for it. Seeding kilograms and correcting a moment later would
    // put a pounds lifter one fast tap away from a silently wrong session.
    if (profile.isPending) return []
    return (plan.data?.exercises ?? []).flatMap((entry) =>
      Array.from({ length: Math.max(1, entry.target_sets ?? 1) }, () => ({
        key: nextKey(),
        exercise_id: entry.exercise_id,
        exercise_name: entry.name ?? 'Exercise',
        category: entry.category ?? 'strength',
        weight: '',
        weight_unit: preferred,
        reps: entry.target_reps != null ? String(entry.target_reps) : '',
        duration: '',
        is_warmup: false,
      })),
    )
  }, [drafts, query.data, plan.data, preferred, profile.isPending])

  const byExercise = useMemo(() => {
    const groups: { exerciseId: number; name: string; sets: DraftSet[] }[] = []
    for (const set of sets) {
      const existing = groups.find((group) => group.exerciseId === set.exercise_id)
      if (existing) existing.sets.push(set)
      else groups.push({ exerciseId: set.exercise_id, name: set.exercise_name, sets: [set] })
    }
    return groups
  }, [sets])

  const logged = useMemo(() => sets.filter(hasData), [sets])
  // In kilograms, because that is what the card underneath it says and what the
  // server will store. Summing the raw numbers would show a pounds session at
  // 2.2x until it saved and the figure silently corrected itself.
  const volume = useMemo(
    () => logged
      .filter((set) => !set.is_warmup)
      .reduce((total, set) => total
        + toKg(Number(set.weight) || 0, set.weight_unit) * (Number(set.reps) || 0), 0),
    [logged],
  )
  const workingSets = logged.filter((set) => !set.is_warmup).length

  function update(key: string, patch: Partial<DraftSet>) {
    setDrafts((current) => (current ?? sets).map((set) =>
      set.key === key ? { ...set, ...patch } : set))
  }

  function remove(key: string) {
    setDrafts((current) => (current ?? sets).filter((set) => set.key !== key))
  }

  function addSet(exerciseId: number, name: string, category: string) {
    const previous = sets.filter((s) => s.exercise_id === exerciseId).at(-1)
    setDrafts((current) => [...(current ?? sets), {
      key: nextKey(),
      exercise_id: exerciseId,
      exercise_name: name,
      category,
      // Carrying the previous set's load forward is what makes logging fast -
      // most sets repeat the one before.
      weight: previous?.weight ?? '',
      weight_unit: previous?.weight_unit ?? preferred,
      reps: previous?.reps ?? '',
      duration: previous?.duration ?? '',
      is_warmup: false,
    }])
  }

  // Sets the whole exercise, not the row. You do not load a bar in pounds for
  // set two, and per-set toggles would be a decision on every line.
  function setUnit(exerciseId: number, unit: WeightUnit) {
    setDrafts((current) => (current ?? sets).map((set) =>
      set.exercise_id === exerciseId ? { ...set, weight_unit: unit } : set))
  }

  function addExercise(exercise: Exercise) {
    addSet(exercise.id, exercise.name, exercise.category)
  }

  function finish() {
    save.mutate(
      { sets: logged.map(toPayload), finished_at: new Date().toISOString() },
      { onSuccess: () => navigate('/training') },
    )
  }

  return (
    <>
      <PageHeader
        storyKind="training"
        title={query.data?.name ?? 'Workout'}
        description={query.data?.date}
        icon={Dumbbell}
        accent="fitness"
        actions={
          <div className="flex items-center gap-2">
            <Button size="sm" icon={Timer} onClick={() => setRestOpen(true)}>Rest</Button>
            <Button
              size="sm" variant="primary" onClick={finish}
              loading={save.isPending} disabled={logged.length === 0}
            >
              Finish
            </Button>
          </div>
        }
      />

      <QueryBoundary query={query} loading={<SkeletonGrid />}>
        {(workout: Workout) => (
          <RevealGroup className="flex flex-col gap-4" step={0.05}>
            <Reveal>
              <Card bodyClassName="flex flex-wrap items-center gap-6">
                <div>
                  <p className="tabular text-metric text-ink">{workingSets}</p>
                  <p className="text-label text-ink-muted">working sets</p>
                </div>
                <div>
                  <p className="tabular text-metric text-ink">
                    {Math.round(volume).toLocaleString()}
                  </p>
                  <p className="text-label text-ink-muted">volume (kg × reps)</p>
                </div>
                {workout.finished_at && <Badge tone="success">Finished</Badge>}
                {save.isError && (
                  <Badge tone="danger">Could not save — your sets are still here</Badge>
                )}
              </Card>
            </Reveal>

            {byExercise.length === 0 ? (
              <Reveal>
                <EmptyState
                  icon={Dumbbell}
                  title="Nothing logged yet"
                  description="Add an exercise and start recording sets."
                  action={
                    <Button variant="primary" icon={Plus} onClick={() => setPickerOpen(true)}>
                      Add exercise
                    </Button>
                  }
                />
              </Reveal>
            ) : (
              <>
                {byExercise.map((group) => (
                  <Reveal key={group.exerciseId} variants={slideIn}>
                    <ExerciseBlock
                      exerciseId={group.exerciseId}
                      workoutId={id}
                      name={group.name}
                      sets={group.sets}
                      onChange={update}
                      onRemove={remove}
                      onAddSet={addSet}
                      onUnit={setUnit}
                      onRest={() => setRestOpen(true)}
                    />
                  </Reveal>
                ))}
                <Reveal>
                  <Button icon={Plus} onClick={() => setPickerOpen(true)} className="w-full">
                    Add exercise
                  </Button>
                </Reveal>
              </>
            )}

            <Reveal>
              <p className="text-center text-meta text-ink-subtle">
                <TrendingUp size={12} className="mr-1 inline" aria-hidden />
                Finishing saves the session and updates Strength, Stamina and Agility.
              </p>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>

      <ExercisePicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={addExercise}
      />
      <RestTimer open={restOpen} onClose={() => setRestOpen(false)} />
    </>
  )
}
