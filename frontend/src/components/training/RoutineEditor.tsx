import { useState } from 'react'
import { m } from 'motion/react'
import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react'

import type { Exercise, Routine, RoutineExercise } from '../../api/types'
import { useSaveRoutine } from '../../api/queries'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { ExercisePicker } from './ExercisePicker'
import { spring } from '../../lib/motion'

const SPLITS = [
  { value: 'push-pull-legs', label: 'Push / Pull / Legs' },
  { value: 'upper-lower', label: 'Upper / Lower' },
  { value: 'full-body', label: 'Full body' },
  { value: 'custom', label: 'Custom' },
]

interface RoutineEditorProps {
  open: boolean
  onClose: () => void
  /** Null creates a new routine; a routine edits it in place. */
  routine: Routine | null
}

export function RoutineEditor({ open, onClose, routine }: RoutineEditorProps) {
  const save = useSaveRoutine()

  const [name, setName] = useState(routine?.name ?? '')
  const [split, setSplit] = useState(routine?.split_type ?? 'custom')
  const [exercises, setExercises] = useState<RoutineExercise[]>(routine?.exercises ?? [])
  const [picking, setPicking] = useState(false)

  function add(exercise: Exercise) {
    setExercises((current) => [...current, {
      exercise_id: exercise.id,
      name: exercise.name,
      category: exercise.category,
      primary_muscle: exercise.primary_muscle,
      target_sets: exercise.category === 'strength' ? 3 : 1,
      target_reps: exercise.category === 'strength' ? 8 : null,
    }])
  }

  function update(index: number, patch: Partial<RoutineExercise>) {
    setExercises((current) =>
      current.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))
  }

  function move(index: number, delta: number) {
    setExercises((current) => {
      const next = [...current]
      const target = index + delta
      if (target < 0 || target >= next.length) return current
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    save.mutate(
      {
        id: routine?.id,
        name: name.trim(),
        split_type: split,
        exercises: exercises.map((entry, position) => ({ ...entry, position })),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title={routine ? 'Edit routine' : 'New routine'}
        description="A routine is a plan, not a log. Starting one pre-fills the session; what you actually lift is still what gets scored."
        size="lg"
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">Name</span>
              <input
                value={name} required autoFocus
                onChange={(event) => setName(event.target.value)}
                placeholder="Push day"
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">Split</span>
              <select
                value={split}
                onChange={(event) => setSplit(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
              >
                {SPLITS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="flex flex-col gap-2">
            <div className="grid grid-cols-[1.5rem_1fr_3.5rem_3.5rem_1.5rem] items-center gap-2 text-caption uppercase tracking-wide text-ink-subtle">
              <span />
              <span>Exercise</span>
              <span className="text-center">Sets</span>
              <span className="text-center">Reps</span>
              <span />
            </div>

            {exercises.length === 0 && (
              <p className="py-3 text-label text-ink-subtle">
                No exercises yet. Add the ones you actually do on this day.
              </p>
            )}

            {exercises.map((entry, index) => (
              <m.div
                key={`${entry.exercise_id}-${index}`}
                layout
                transition={spring.snappy}
                className="grid grid-cols-[1.5rem_1fr_3.5rem_3.5rem_1.5rem] items-center gap-2"
              >
                <div className="flex flex-col items-center text-ink-subtle">
                  <button
                    type="button" onClick={() => move(index, -1)}
                    disabled={index === 0} aria-label={`Move ${entry.name} up`}
                    className="leading-none transition-colors hover:text-ink disabled:opacity-25"
                  >
                    <ChevronUp size={13} aria-hidden />
                  </button>
                  <button
                    type="button" onClick={() => move(index, 1)}
                    disabled={index === exercises.length - 1}
                    aria-label={`Move ${entry.name} down`}
                    className="leading-none transition-colors hover:text-ink disabled:opacity-25"
                  >
                    <ChevronDown size={13} aria-hidden />
                  </button>
                </div>
                <span className="truncate text-label text-ink">{entry.name}</span>
                <input
                  type="number" min="1" inputMode="numeric"
                  value={entry.target_sets ?? ''}
                  onChange={(event) => update(index, {
                    target_sets: event.target.value === '' ? null : Number(event.target.value),
                  })}
                  aria-label={`Target sets for ${entry.name}`}
                  className="rounded-md border border-line bg-surface-base px-2 py-1.5 text-center text-label tabular text-ink outline-none focus:border-brand"
                />
                <input
                  type="number" min="1" inputMode="numeric"
                  value={entry.target_reps ?? ''}
                  onChange={(event) => update(index, {
                    target_reps: event.target.value === '' ? null : Number(event.target.value),
                  })}
                  aria-label={`Target reps for ${entry.name}`}
                  placeholder="—"
                  className="rounded-md border border-line bg-surface-base px-2 py-1.5 text-center text-label tabular text-ink outline-none focus:border-brand"
                />
                <button
                  type="button"
                  onClick={() => setExercises((current) =>
                    current.filter((_, i) => i !== index))}
                  aria-label={`Remove ${entry.name}`}
                  className="text-ink-subtle transition-colors hover:text-danger"
                >
                  <Trash2 size={14} />
                </button>
              </m.div>
            ))}

            <Button
              type="button" size="sm" variant="ghost" icon={Plus}
              onClick={() => setPicking(true)} className="self-start"
            >
              Add exercise
            </Button>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={save.isPending}>
              {routine ? 'Save changes' : 'Create routine'}
            </Button>
          </div>
        </form>
      </Modal>

      <ExercisePicker open={picking} onClose={() => setPicking(false)} onPick={add} />
    </>
  )
}
