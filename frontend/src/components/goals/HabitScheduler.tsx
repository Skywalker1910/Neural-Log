import { useState } from 'react'
import { Info } from 'lucide-react'

import type { HabitStat, ScheduleType } from '../../api/types'
import { useUpdateHabit } from '../../api/queries'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { cn } from '../../lib/cn'

/** Monday first, matching the Python side's weekday() where Monday is 0. */
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const SCHEDULES: { value: ScheduleType; label: string; hint: string }[] = [
  { value: 'daily', label: 'Every day', hint: 'Expected every single day' },
  { value: 'weekdays', label: 'Weekdays', hint: 'Monday to Friday' },
  { value: 'days', label: 'Certain days', hint: 'Pick the days below' },
  {
    value: 'times-per-week',
    label: 'N times a week',
    hint: 'Any days you like — only the weekly count matters',
  },
]

interface HabitSchedulerProps {
  open: boolean
  onClose: () => void
  habit: HabitStat
}

export function HabitScheduler({ open, onClose, habit }: HabitSchedulerProps) {
  const update = useUpdateHabit()

  const [name, setName] = useState(habit.name)
  const [weight, setWeight] = useState(String(habit.weight))
  const [type, setType] = useState<ScheduleType>(habit.schedule_type)
  const [days, setDays] = useState<number[]>(habit.schedule_days ?? [])
  const [target, setTarget] = useState(
    habit.target_per_week != null ? String(habit.target_per_week) : '3',
  )

  function toggleDay(index: number) {
    setDays((current) =>
      current.includes(index)
        ? current.filter((d) => d !== index)
        : [...current, index].sort((a, b) => a - b))
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    update.mutate(
      {
        id: habit.id,
        name: name.trim() || habit.name,
        weight: Number(weight) || habit.weight,
        schedule_type: type,
        schedule_days: type === 'days' ? days : [],
        target_per_week: type === 'times-per-week' ? Number(target) || 3 : null,
      },
      { onSuccess: onClose },
    )
  }

  const selectedHint = SCHEDULES.find((s) => s.value === type)?.hint

  return (
    <Modal open={open} onClose={onClose} title="Habit" description={habit.group_name}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <div>
          <span className="mb-1 block text-meta text-ink-muted">Schedule</span>
          <div className="grid grid-cols-2 gap-1.5">
            {SCHEDULES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setType(option.value)}
                aria-pressed={type === option.value}
                className={cn(
                  'rounded-md border px-3 py-2 text-left text-meta transition-colors',
                  type === option.value
                    ? 'border-goals bg-goals/15 text-goals'
                    : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          {selectedHint && (
            <p className="mt-1 text-caption text-ink-subtle">{selectedHint}</p>
          )}
        </div>

        {type === 'days' && (
          <div>
            <span className="mb-1 block text-meta text-ink-muted">Which days</span>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleDay(index)}
                  aria-pressed={days.includes(index)}
                  className={cn(
                    'w-12 rounded-md border py-1.5 text-meta transition-colors',
                    days.includes(index)
                      ? 'border-goals bg-goals/15 text-goals'
                      : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {days.length === 0 && (
              <p className="mt-1 text-caption text-warning">
                Pick at least one day, or this habit is never due.
              </p>
            )}
          </div>
        )}

        {type === 'times-per-week' && (
          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">Times per week</span>
            <input
              type="number" min="1" max="7" value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="w-24 rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
            <span className="flex items-start gap-1.5 text-caption text-ink-subtle">
              <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
              It stays offerable every day — there is no honest way to say which
              day it is "due". Whether you are behind is a weekly question, and
              the habit list answers it.
            </span>
          </label>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Weight</span>
          <input
            type="number" min="0" max="5" value={weight}
            onChange={(event) => setWeight(event.target.value)}
            className="w-24 rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
          <span className="text-caption text-ink-subtle">
            How much this counts toward your daily score, 0 to 5.
          </span>
        </label>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            type="submit" variant="primary" loading={update.isPending}
            disabled={type === 'days' && days.length === 0}
          >
            Save habit
          </Button>
        </div>
      </form>
    </Modal>
  )
}
