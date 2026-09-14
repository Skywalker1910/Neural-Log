import { useMemo, useState } from 'react'
import { Dumbbell, Search } from 'lucide-react'

import type { Exercise, MuscleGroup } from '../../api/types'
import { useExercises } from '../../api/queries'
import { Badge } from '../ui/Badge'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import { QueryBoundary } from '../ui/QueryBoundary'
import { SkeletonGrid } from '../ui/Skeleton'
import { cn } from '../../lib/cn'

/** Grouped the way people think about training, not alphabetically. */
const MUSCLE_ORDER: MuscleGroup[] = [
  'chest', 'back', 'shoulders', 'biceps', 'triceps', 'forearms',
  'quads', 'hamstrings', 'glutes', 'calves', 'core', 'full-body', 'cardio',
]

const CATEGORIES = [
  { value: '', label: 'All' },
  { value: 'strength', label: 'Strength' },
  { value: 'cardio', label: 'Cardio' },
  { value: 'mobility', label: 'Mobility' },
]

interface ExercisePickerProps {
  open: boolean
  onClose: () => void
  onPick: (exercise: Exercise) => void
}

export function ExercisePicker({ open, onClose, onPick }: ExercisePickerProps) {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [muscle, setMuscle] = useState('')

  // Filtering happens server-side so the query key changes and results cache per
  // filter combination rather than refiltering 85 rows on every keystroke.
  const query = useExercises({ q: search, category, muscle })

  const grouped = useMemo(() => {
    const byMuscle = new Map<string, Exercise[]>()
    for (const exercise of query.data?.exercises ?? []) {
      const list = byMuscle.get(exercise.primary_muscle) ?? []
      list.push(exercise)
      byMuscle.set(exercise.primary_muscle, list)
    }
    return MUSCLE_ORDER
      .filter((group) => byMuscle.has(group))
      .map((group) => ({ muscle: group, exercises: byMuscle.get(group)! }))
  }, [query.data])

  return (
    <Modal open={open} onClose={onClose} title="Add an exercise" size="lg">
      <div className="mb-4 flex flex-col gap-3">
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
            placeholder="Search exercises"
            aria-label="Search exercises"
            className="w-full rounded-md border border-line bg-surface-base py-2 pl-9 pr-3 text-label text-ink outline-none transition-colors focus:border-brand"
          />
        </label>

        <div className="flex flex-wrap gap-1.5">
          {CATEGORIES.map((option) => (
            <button
              key={option.value || 'all'}
              type="button"
              onClick={() => setCategory(option.value)}
              className={cn(
                'rounded-full border px-3 py-1 text-meta transition-colors',
                category === option.value
                  ? 'border-fitness bg-fitness/15 text-fitness'
                  : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              {option.label}
            </button>
          ))}
          <span className="mx-1 w-px bg-line" aria-hidden />
          <button
            type="button"
            onClick={() => setMuscle('')}
            className={cn(
              'rounded-full border px-3 py-1 text-meta transition-colors',
              muscle === ''
                ? 'border-brand bg-brand/15 text-ink'
                : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            Any muscle
          </button>
          {MUSCLE_ORDER.map((group) => (
            <button
              key={group}
              type="button"
              onClick={() => setMuscle(group === muscle ? '' : group)}
              className={cn(
                'rounded-full border px-3 py-1 text-meta capitalize transition-colors',
                muscle === group
                  ? 'border-brand bg-brand/15 text-ink'
                  : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
              )}
            >
              {group.replace('-', ' ')}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-[50vh] overflow-y-auto">
        <QueryBoundary
          query={query}
          loading={<SkeletonGrid />}
          isEmpty={(data) => data.exercises.length === 0}
          empty={
            <EmptyState
              icon={Dumbbell}
              title="Nothing matches that"
              description="Try a different muscle group, or clear the search."
            />
          }
        >
          {() => (
            <div className="flex flex-col gap-4">
              {grouped.map((group) => (
                <section key={group.muscle}>
                  <h3 className="mb-2 text-caption uppercase tracking-wide text-ink-subtle">
                    {group.muscle.replace('-', ' ')}
                  </h3>
                  <div className="flex flex-col gap-1.5">
                    {group.exercises.map((exercise) => (
                      <button
                        key={exercise.id}
                        type="button"
                        onClick={() => {
                          onPick(exercise)
                          onClose()
                        }}
                        className="flex items-center gap-3 rounded-md border border-line bg-surface-card px-3 py-2 text-left transition-colors hover:border-line-strong hover:bg-surface-raised"
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-label text-ink">
                            {exercise.name}
                          </span>
                          <span className="block truncate text-meta text-ink-subtle">
                            {exercise.equipment} · {exercise.difficulty}
                            {exercise.secondary_muscles.length > 0 &&
                              ` · also ${exercise.secondary_muscles.join(', ')}`}
                          </span>
                        </span>
                        {exercise.is_compound && <Badge tone="neutral">compound</Badge>}
                      </button>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </QueryBoundary>
      </div>
    </Modal>
  )
}
