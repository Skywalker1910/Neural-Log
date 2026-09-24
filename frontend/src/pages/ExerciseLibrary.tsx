import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { ArrowLeft, Dumbbell, Search } from 'lucide-react'

import { useExercises } from '../api/queries'
import type { Exercise, MuscleGroup } from '../api/types'
import { ExerciseAnimation } from '../components/training/ExerciseAnimation'
import { ExerciseDemonstration } from '../components/training/ExerciseDemonstration'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { patternLabel } from '../lib/movementPatterns'

/**
 * The exercise library, as somewhere you can actually go.
 *
 * It existed before this page, but only inside the "add an exercise" modal - so
 * the only way to see what the app knew about was to start a workout you did not
 * want or begin a routine you had no intention of saving. A reference you can
 * only reach by pretending to do something else is not a reference.
 *
 * Its own route rather than another card on Training: the page is already long,
 * and this is a thing you browse rather than a thing you check.
 */

const MUSCLES: { value: '' | MuscleGroup; label: string }[] = [
  { value: '', label: 'All muscles' },
  { value: 'chest', label: 'Chest' },
  { value: 'back', label: 'Back' },
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'biceps', label: 'Biceps' },
  { value: 'triceps', label: 'Triceps' },
  { value: 'forearms', label: 'Forearms' },
  { value: 'quads', label: 'Quads' },
  { value: 'hamstrings', label: 'Hamstrings' },
  { value: 'glutes', label: 'Glutes' },
  { value: 'calves', label: 'Calves' },
  { value: 'core', label: 'Core' },
  { value: 'full-body', label: 'Full body' },
  { value: 'cardio', label: 'Cardio' },
]

const CATEGORIES = [
  { value: '', label: 'Everything' },
  { value: 'strength', label: 'Strength' },
  { value: 'cardio', label: 'Cardio' },
  { value: 'mobility', label: 'Mobility' },
]

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'shrink-0 rounded-pill border px-3 py-1 text-meta transition-colors duration-200 ease-apple',
        active
          ? 'border-fitness bg-fitness/15 text-fitness'
          : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
      )}
    >
      {children}
    </button>
  )
}

function ExerciseCard({ exercise }: { exercise: Exercise }) {
  const pattern = patternLabel(exercise.movement_pattern)

  return (
    <div className="flex min-w-0 flex-col gap-3 rounded-lg border border-line bg-surface-card p-4">
      <div className="flex min-w-0 items-start gap-3">
        <ExerciseAnimation pattern={exercise.movement_pattern} name={exercise.name} equipment={exercise.equipment} size={86} />

        <div className="min-w-0 flex-1">
          <p className="text-section text-ink">{exercise.name}</p>
          <p className="mt-0.5 text-meta text-ink-subtle">
            {exercise.equipment} · {exercise.difficulty}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone="neutral">{exercise.primary_muscle.replace('-', ' ')}</Badge>
            {exercise.is_compound && <Badge tone="success">compound</Badge>}
            {pattern && <Badge tone="neutral">{pattern}</Badge>}
          </div>
        </div>
      </div>

      {exercise.secondary_muscles.length > 0 && (
        <p className="text-meta text-ink-subtle">
          Also works {exercise.secondary_muscles.join(', ')}
        </p>
      )}

      <details className="text-meta text-ink-muted">
        <summary className="mb-3 cursor-pointer">Explore the movement</summary>
        <ExerciseDemonstration exercise={exercise} />
      </details>

      {exercise.instructions.length > 0 && (
        <ul className="flex flex-col gap-1">
          {exercise.instructions.map((line, index) => (
            <li key={index} className="flex gap-2 text-meta text-ink-muted">
              <span className="tabular shrink-0 text-ink-subtle">{index + 1}</span>
              <span className="min-w-0">{line}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function ExerciseLibrary() {
  const [search, setSearch] = useState('')
  const [muscle, setMuscle] = useState<'' | MuscleGroup>('')
  const [category, setCategory] = useState('')

  /*
    The whole library is fetched once and filtered here rather than refetching
    per keystroke. It is 136 rows that change only when the app ships a new
    version - useExercises already caches it for half an hour - and searching
    over an array nobody has to wait for is the difference between a list that
    filters as you type and one that flickers.
  */
  const query = useExercises()

  const groups = useMemo(() => {
    const all = query.data?.exercises ?? []
    const needle = search.trim().toLowerCase()

    const matching = all.filter((exercise) => {
      if (muscle && exercise.primary_muscle !== muscle) return false
      if (category && exercise.category !== category) return false
      if (!needle) return true
      return (
        exercise.name.toLowerCase().includes(needle) ||
        exercise.equipment.toLowerCase().includes(needle) ||
        exercise.primary_muscle.includes(needle)
      )
    })

    const byMuscle = new Map<string, Exercise[]>()
    for (const exercise of matching) {
      const list = byMuscle.get(exercise.primary_muscle) ?? []
      list.push(exercise)
      byMuscle.set(exercise.primary_muscle, list)
    }
    return [...byMuscle.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, exercises]) => ({ muscle: key, exercises }))
  }, [query.data, search, muscle, category])

  const total = query.data?.exercises.length ?? 0
  const shown = groups.reduce((sum, group) => sum + group.exercises.length, 0)

  return (
    <>
      <PageHeader
        storyKind="training"
        title="Exercise library"
        description={`${total} exercises, grouped by the muscle they target. Every one shows the shape of its movement.`}
        icon={Dumbbell}
        accent="fitness"
        actions={
          <Link to="/training">
            <Button variant="secondary" icon={ArrowLeft}>
              Training
            </Button>
          </Link>
        }
      />

      <RevealGroup className="flex flex-col gap-4" step={0.04}>
        <Reveal>
          <Card bodyClassName="flex flex-col gap-3">
            <label className="relative block">
              <Search
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-subtle"
                aria-hidden
              />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name, equipment or muscle"
                aria-label="Search exercises"
                className="w-full rounded-md border border-line bg-surface-base py-2 pl-9 pr-3 text-label text-ink outline-none transition-colors focus:border-brand"
              />
            </label>

            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((option) => (
                <Chip
                  key={option.value || 'all'}
                  active={category === option.value}
                  onClick={() => setCategory(option.value)}
                >
                  {option.label}
                </Chip>
              ))}
            </div>

            <div className="flex flex-wrap gap-1.5">
              {MUSCLES.map((option) => (
                <Chip
                  key={option.value || 'all'}
                  active={muscle === option.value}
                  onClick={() => setMuscle(option.value)}
                >
                  {option.label}
                </Chip>
              ))}
            </div>

            <p className="text-meta text-ink-subtle">
              Showing {shown} of {total}. Open a movement to pause, slow down, or inspect a position.
              The written cues explain each exercise’s setup.
            </p>
          </Card>
        </Reveal>

        <QueryBoundary query={query} loading={<SkeletonGrid />}>
          {() =>
            groups.length === 0 ? (
              <Reveal>
                <Card>
                  <EmptyState
                    icon={Search}
                    title="Nothing matches that"
                    description="Try a different muscle, or clear the filters."
                  />
                </Card>
              </Reveal>
            ) : (
              <>
                {groups.map((group) => (
                  <Reveal key={group.muscle}>
                    <section>
                      <h2 className="mb-2 text-caption uppercase tracking-wide text-ink-subtle">
                        {group.muscle.replace('-', ' ')} · {group.exercises.length}
                      </h2>
                      <div className="grid gap-3 lg:grid-cols-2">
                        {group.exercises.map((exercise) => (
                          <ExerciseCard key={exercise.id} exercise={exercise} />
                        ))}
                      </div>
                    </section>
                  </Reveal>
                ))}
              </>
            )
          }
        </QueryBoundary>
      </RevealGroup>
    </>
  )
}
