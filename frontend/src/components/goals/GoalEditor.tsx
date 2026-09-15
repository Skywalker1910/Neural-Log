import { useState } from 'react'
import { m } from 'motion/react'
import { Info, Link2, Plus, Trash2 } from 'lucide-react'

import type { Goal, GoalCategory, GoalsSummary, GoalStatus } from '../../api/types'
import { useSaveGoal } from '../../api/queries'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { cn } from '../../lib/cn'
import { spring } from '../../lib/motion'

const CATEGORIES: { value: GoalCategory; label: string; accent: string }[] = [
  { value: 'fitness', label: 'Fitness', accent: 'fitness' },
  { value: 'learning', label: 'Learning', accent: 'learning' },
  { value: 'lifestyle', label: 'Lifestyle', accent: 'lifestyle' },
  { value: 'career', label: 'Career', accent: 'goals' },
  { value: 'finance', label: 'Finance', accent: 'discipline' },
  { value: 'other', label: 'Other', accent: 'goals' },
]

const STATUSES: GoalStatus[] = ['active', 'paused', 'achieved', 'abandoned']

interface GoalEditorProps {
  open: boolean
  onClose: () => void
  /** Null creates a new goal; a goal edits it in place. */
  goal: Goal | null
  habits: GoalsSummary['habits']
}

export function GoalEditor({ open, onClose, goal, habits }: GoalEditorProps) {
  const save = useSaveGoal()

  const [title, setTitle] = useState(goal?.title ?? '')
  const [description, setDescription] = useState(goal?.description ?? '')
  const [category, setCategory] = useState<GoalCategory>(goal?.category ?? 'other')
  const [status, setStatus] = useState<GoalStatus>(goal?.status ?? 'active')
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? '')
  const [metricName, setMetricName] = useState(goal?.metric_name ?? '')
  const [targetValue, setTargetValue] = useState(
    goal?.target_value != null ? String(goal.target_value) : '',
  )
  const [currentValue, setCurrentValue] = useState(
    goal?.current_value != null ? String(goal.current_value) : '',
  )
  const [linked, setLinked] = useState<number[]>(goal?.habit_ids ?? [])
  const [milestones, setMilestones] = useState<string[]>([])
  const [draft, setDraft] = useState('')

  const accent = CATEGORIES.find((c) => c.value === category)?.accent ?? 'goals'

  function toggleHabit(id: number) {
    setLinked((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id])
  }

  function addMilestone() {
    const text = draft.trim()
    if (!text) return
    setMilestones((current) => [...current, text])
    setDraft('')
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!title.trim()) return

    save.mutate(
      {
        id: goal?.id,
        title: title.trim(),
        description: description.trim() || null,
        category,
        accent,
        status,
        target_date: targetDate || null,
        metric_name: metricName.trim() || null,
        target_value: targetValue === '' ? null : Number(targetValue),
        current_value: currentValue === '' ? 0 : Number(currentValue),
        habit_ids: linked,
        // Only sent on create; editing milestones happens on the goal card,
        // where you can tick them off rather than retype them.
        ...(goal ? {} : { milestones }),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={goal ? 'Edit goal' : 'New goal'}
      description="Link habits to a goal and its progress comes from what you actually did, rather than a number you keep updating by hand."
      size="lg"
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">What do you want to do?</span>
          <input
            value={title} required autoFocus
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Run a half marathon"
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Why, or how — optional</span>
          <textarea
            value={description} rows={2}
            onChange={(event) => setDescription(event.target.value)}
            className="w-full resize-y rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <div>
          <span className="mb-1 block text-meta text-ink-muted">Category</span>
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setCategory(option.value)}
                aria-pressed={category === option.value}
                className={cn(
                  'rounded-full border px-3 py-1 text-meta transition-colors',
                  category === option.value
                    ? 'border-goals bg-goals/15 text-goals'
                    : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">Target date — optional</span>
            <input
              type="date" value={targetDate}
              onChange={(event) => setTargetDate(event.target.value)}
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
          </label>

          {goal && (
            <div>
              <span className="mb-1 block text-meta text-ink-muted">Status</span>
              <div className="flex flex-wrap gap-1.5">
                {STATUSES.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setStatus(option)}
                    aria-pressed={status === option}
                    className={cn(
                      'rounded-md border px-2.5 py-1.5 text-meta capitalize transition-colors',
                      status === option
                        ? 'border-goals bg-goals/15 text-goals'
                        : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                    )}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* --- habit linking: the evidenced route --- */}
        <div>
          <span className="mb-1 flex items-center gap-1.5 text-meta text-ink-muted">
            <Link2 size={13} aria-hidden />
            Habits that move this goal
          </span>
          <div className="max-h-40 overflow-y-auto rounded-md border border-line bg-surface-base p-2">
            {habits.length === 0 ? (
              <p className="text-caption text-ink-subtle">No habits yet.</p>
            ) : (
              <div className="flex flex-col gap-1">
                {habits.map((habit) => (
                  <button
                    key={habit.id}
                    type="button"
                    onClick={() => toggleHabit(habit.id)}
                    aria-pressed={linked.includes(habit.id)}
                    className={cn(
                      'flex items-center gap-2 rounded px-2 py-1.5 text-left text-meta transition-colors',
                      linked.includes(habit.id)
                        ? 'bg-goals/15 text-goals'
                        : 'text-ink-muted hover:bg-surface-raised hover:text-ink',
                    )}
                  >
                    <span className={cn(
                      'flex size-4 shrink-0 items-center justify-center rounded border text-caption',
                      linked.includes(habit.id)
                        ? 'border-goals bg-goals/30'
                        : 'border-line',
                    )}>
                      {linked.includes(habit.id) ? '✓' : ''}
                    </span>
                    <span className="min-w-0 flex-1 truncate">{habit.name}</span>
                    <span className="shrink-0 text-caption text-ink-subtle">
                      {habit.group_name}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <p className="mt-1 flex items-start gap-1.5 text-caption text-ink-subtle">
            <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
            Link at least one and progress is measured from your actual
            completions. Without a link it falls back to milestones, then to a
            number you maintain yourself — the goal card always says which.
          </p>
        </div>

        {/* --- the manual fallbacks --- */}
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">Measure — optional</span>
            <input
              value={metricName}
              onChange={(event) => setMetricName(event.target.value)}
              placeholder="books, km"
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">Target</span>
            <input
              type="number" min="0" step="any" value={targetValue}
              onChange={(event) => setTargetValue(event.target.value)}
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">So far</span>
            <input
              type="number" min="0" step="any" value={currentValue}
              onChange={(event) => setCurrentValue(event.target.value)}
              className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
            />
          </label>
        </div>

        {!goal && (
          <div>
            <span className="mb-1 block text-meta text-ink-muted">
              Milestones — optional
            </span>
            <div className="flex flex-col gap-1.5">
              {milestones.map((text, index) => (
                <m.div
                  key={`${text}-${index}`}
                  layout
                  transition={spring.snappy}
                  className="flex items-center gap-2 rounded-md border border-line bg-surface-base px-3 py-1.5"
                >
                  <span className="min-w-0 flex-1 truncate text-meta text-ink">{text}</span>
                  <button
                    type="button"
                    onClick={() => setMilestones((c) => c.filter((_, i) => i !== index))}
                    aria-label={`Remove ${text}`}
                    className="shrink-0 text-ink-subtle transition-colors hover:text-danger"
                  >
                    <Trash2 size={13} />
                  </button>
                </m.div>
              ))}

              <div className="flex gap-2">
                <input
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      // Otherwise Enter submits the whole form while you are
                      // still listing milestones.
                      event.preventDefault()
                      addMilestone()
                    }
                  }}
                  placeholder="First checkpoint"
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface-base px-3 py-1.5 text-label text-ink outline-none focus:border-brand"
                />
                <Button type="button" size="sm" variant="secondary" icon={Plus}
                        onClick={addMilestone} className="shrink-0">
                  Add
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {goal ? 'Save goal' : 'Create goal'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
