import { useMemo, useState } from 'react'
import { m } from 'motion/react'
import {
  AlarmClock, Check, CheckCircle2, Flame, Link2, ListTodo, Pencil, Plus,
  Repeat, Target, Trash2, Trophy,
} from 'lucide-react'

import type {
  Goal, GoalProgress, GoalsSummary, HabitStat, Task,
} from '../api/types'
import {
  useAddMilestone, useDeleteGoal, useDeleteTask, useGoalsSummary, useHabits,
  useSaveTask, useUpdateMilestone,
} from '../api/queries'
import { GoalEditor } from '../components/goals/GoalEditor'
import { HabitScheduler } from '../components/goals/HabitScheduler'
import { PageHeader } from '../components/layout/PageHeader'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { cn } from '../lib/cn'
import { todayISO } from '../lib/date'
import { spring } from '../lib/motion'

const DAY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

/**
 * Where a progress number came from, said out loud.
 *
 * The whole point of R6's progress model is that a percentage derived from real
 * completions and one typed in by hand are not the same claim. Showing both as a
 * bare number would erase exactly the distinction the backend works to preserve.
 */
const SOURCE_LABEL: Record<GoalProgress['source'], { text: string; tone: 'success' | 'info' | 'neutral' }> = {
  habits: { text: 'from your habits', tone: 'success' },
  milestones: { text: 'from milestones', tone: 'info' },
  metric: { text: 'self-reported', tone: 'neutral' },
  none: { text: 'nothing to measure', tone: 'neutral' },
}

function ProgressBar({ progress }: { progress: GoalProgress }) {
  if (progress.percent == null) {
    return (
      <p className="text-meta text-ink-subtle">
        No measure on this one — link a habit, add milestones, or give it a number.
      </p>
    )
  }

  const label = SOURCE_LABEL[progress.source]

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="tabular text-section text-ink">{progress.percent}%</span>
        <Badge tone={label.tone}>{label.text}</Badge>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface-raised">
        <m.div
          className={cn('h-full rounded-full',
            progress.source === 'habits' ? 'bg-success' : 'bg-goals')}
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, progress.percent)}%` }}
          transition={spring.soft}
        />
      </div>
    </div>
  )
}

function Deadline({ goal }: { goal: Goal }) {
  if (!goal.target_date) return null
  const days = goal.days_remaining

  if (days == null) return null
  if (goal.status === 'achieved') {
    return <Badge tone="success">achieved {goal.achieved_on}</Badge>
  }
  if (days < 0) return <Badge tone="danger">{Math.abs(days)} days overdue</Badge>
  if (days <= 7) return <Badge tone="warning">{days} days left</Badge>
  return <span className="text-meta text-ink-subtle">by {goal.target_date}</span>
}

function GoalCard({
  goal, onEdit, onDelete,
}: {
  goal: Goal
  onEdit: () => void
  onDelete: () => void
}) {
  const updateMilestone = useUpdateMilestone()
  const addMilestone = useAddMilestone(goal.id)
  const [draft, setDraft] = useState('')

  const dimmed = goal.status === 'achieved' || goal.status === 'abandoned'

  return (
    <Card
      title={goal.title}
      subtitle={goal.description ?? undefined}
      icon={goal.status === 'achieved' ? Trophy : Target}
      accent="goals"
      // min-w-0 because a grid item defaults to min-width:auto: without it the
      // card refuses to shrink below its header's intrinsic width and pushes the
      // page into horizontal scroll on a phone.
      className={cn('min-w-0', dimmed && 'opacity-70')}
      action={
        <div className="flex shrink-0 gap-1">
          <Button size="sm" variant="ghost" icon={Pencil}
                  aria-label={`Edit ${goal.title}`} onClick={onEdit} />
          <Button size="sm" variant="ghost" icon={Trash2}
                  aria-label={`Archive ${goal.title}`} onClick={onDelete} />
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">{goal.category}</Badge>
          {goal.status !== 'active' && <Badge tone="neutral">{goal.status}</Badge>}
          <Deadline goal={goal} />
        </div>

        <ProgressBar progress={goal.progress} />

        {goal.progress.source === 'habits' && (
          <div className="flex flex-col gap-1">
            {goal.progress.linked_habits.map((habit) => (
              <div key={habit.habit_id}
                   className="flex items-center gap-2 text-meta text-ink-subtle">
                <Link2 size={12} className="shrink-0" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{habit.name}</span>
                <span className="tabular shrink-0">
                  {habit.done}/{habit.elapsed_days} days
                </span>
              </div>
            ))}
          </div>
        )}

        {goal.metric_name && goal.target_value != null
          && goal.progress.source !== 'habits' && (
          <p className="tabular text-meta text-ink-muted">
            {goal.current_value} / {goal.target_value} {goal.metric_name}
          </p>
        )}

        {goal.milestones.length > 0 && (
          <div className="flex flex-col gap-1">
            {goal.milestones.map((milestone) => (
              <button
                key={milestone.id}
                type="button"
                onClick={() => updateMilestone.mutate({
                  id: milestone.id, completed: !milestone.completed_on,
                })}
                className="flex items-center gap-2 rounded px-1 py-1 text-left transition-colors hover:bg-surface-raised"
              >
                <span className={cn(
                  'flex size-4 shrink-0 items-center justify-center rounded border',
                  milestone.completed_on
                    ? 'border-success bg-success/25 text-success'
                    : 'border-line',
                )}>
                  {milestone.completed_on && <Check size={11} />}
                </span>
                <span className={cn('min-w-0 flex-1 truncate text-meta',
                  milestone.completed_on ? 'text-ink-subtle line-through' : 'text-ink')}>
                  {milestone.title}
                </span>
                {milestone.completed_on && (
                  <span className="tabular shrink-0 text-caption text-ink-subtle">
                    {milestone.completed_on}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && draft.trim()) {
                addMilestone.mutate({ title: draft.trim() })
                setDraft('')
              }
            }}
            placeholder="Add a milestone"
            aria-label={`Add a milestone to ${goal.title}`}
            className="min-w-0 flex-1 rounded-md border border-line bg-surface-base px-3 py-1.5 text-meta text-ink outline-none focus:border-brand"
          />
        </div>
      </div>
    </Card>
  )
}

function TaskRow({ task, onToggle, onDelete }: {
  task: Task
  onToggle: () => void
  onDelete: () => void
}) {
  const overdue = task.due_date && !task.completed_on && task.due_date < todayISO()

  return (
    <m.div
      layout
      transition={spring.snappy}
      className="flex min-w-0 items-center gap-2 rounded-md border border-line bg-surface-base px-3 py-2"
    >
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={Boolean(task.completed_on)}
        aria-label={`Mark ${task.title} ${task.completed_on ? 'incomplete' : 'complete'}`}
        className={cn(
          'flex size-5 shrink-0 items-center justify-center rounded border transition-colors',
          task.completed_on
            ? 'border-success bg-success/25 text-success'
            : 'border-line hover:border-line-strong',
        )}
      >
        {task.completed_on && <Check size={12} />}
      </button>

      <span className="min-w-0 flex-1">
        <span className={cn('block truncate text-label',
          task.completed_on ? 'text-ink-subtle line-through' : 'text-ink')}>
          {task.title}
        </span>
        {(task.goal_title || task.due_date) && (
          <span className="block truncate text-meta text-ink-subtle">
            {task.goal_title}
            {task.goal_title && task.due_date && ' · '}
            {task.due_date && (
              <span className={cn('tabular', overdue && 'text-danger')}>
                due {task.due_date}
              </span>
            )}
          </span>
        )}
      </span>

      <Button size="sm" variant="ghost" icon={Trash2} className="shrink-0"
              aria-label={`Delete ${task.title}`} onClick={onDelete} />
    </m.div>
  )
}

function HabitRow({ habit, onEdit }: { habit: HabitStat; onEdit: () => void }) {
  const adherence = habit.logged > 0 ? Math.round((habit.done / habit.logged) * 100) : null

  return (
    <div className="flex min-w-0 items-center gap-3 rounded-md border border-line bg-surface-base px-3 py-2">
      <span className="min-w-0 flex-1">
        <span className="block truncate text-label text-ink">{habit.name}</span>
        <span className="flex flex-wrap items-center gap-x-2 text-meta text-ink-subtle">
          {habit.schedule_type === 'daily' && 'every day'}
          {habit.schedule_type === 'weekdays' && 'weekdays'}
          {habit.schedule_type === 'times-per-week'
            && `${habit.target_per_week ?? '?'}× a week`}
          {habit.schedule_type === 'days' && (
            <span className="flex gap-0.5">
              {DAY_LABELS.map((label, index) => (
                <span key={index} className={cn('tabular',
                  habit.schedule_days.includes(index) ? 'text-goals' : 'text-ink-subtle/40')}>
                  {label}
                </span>
              ))}
            </span>
          )}
          {adherence != null && <span className="tabular">{adherence}% kept</span>}
        </span>
      </span>

      {habit.streak > 0 && (
        <span className="tabular flex shrink-0 items-center gap-1 text-meta text-discipline">
          <Flame size={12} aria-hidden />{habit.streak}
        </span>
      )}

      <Button size="sm" variant="ghost" icon={Pencil} className="shrink-0"
              aria-label={`Edit ${habit.name}`} onClick={onEdit} />
    </div>
  )
}

export function Goals() {
  const summary = useGoalsSummary()
  const habits = useHabits()

  const saveTask = useSaveTask()
  const removeTask = useDeleteTask()
  const removeGoal = useDeleteGoal()

  const [editingGoal, setEditingGoal] = useState<Goal | null | undefined>(undefined)
  const [editingHabit, setEditingHabit] = useState<HabitStat | null>(null)
  const [taskDraft, setTaskDraft] = useState('')

  const grouped = useMemo(() => {
    const goals = summary.data?.goals ?? []
    return {
      active: goals.filter((goal) => goal.status === 'active' || goal.status === 'paused'),
      closed: goals.filter((goal) => goal.status === 'achieved' || goal.status === 'abandoned'),
    }
  }, [summary.data])

  function addTask() {
    const title = taskDraft.trim()
    if (!title) return
    saveTask.mutate({ title }, { onSuccess: () => setTaskDraft('') })
  }

  return (
    <>
      <PageHeader
        title="Goals"
        description="Habits are what you repeat; goals are where they are going. Neither is scored on intention."
        icon={Target}
        accent="goals"
        actions={
          <Button size="sm" variant="primary" icon={Plus}
                  onClick={() => setEditingGoal(null)}>
            New goal
          </Button>
        }
      />

      <QueryBoundary query={summary} loading={<SkeletonGrid />}>
        {(data: GoalsSummary) => (
          <RevealGroup className="flex flex-col gap-4">
            <Reveal className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard label="Active" value={data.totals.active}
                        icon={Target} accent="goals" />
              <StatCard label="Achieved" value={data.totals.achieved}
                        icon={Trophy} accent="discipline" />
              <StatCard label="Overdue" value={data.totals.overdue}
                        icon={AlarmClock}
                        accent={data.totals.overdue > 0 ? 'fitness' : 'goals'}
                        hint={data.totals.due_soon ? `${data.totals.due_soon} due soon` : undefined} />
              <StatCard label="Open tasks" value={data.totals.open_tasks}
                        icon={ListTodo} accent="learning" />
            </Reveal>

            {grouped.active.length === 0 && grouped.closed.length === 0 ? (
              <Reveal>
                <EmptyState
                  icon={Target}
                  title="No goals yet"
                  description="A goal linked to habits measures itself from what you actually did. One without them is just a note — useful, but say so."
                  action={
                    <Button variant="primary" icon={Plus}
                            onClick={() => setEditingGoal(null)}>
                      New goal
                    </Button>
                  }
                />
              </Reveal>
            ) : (
              <Reveal className="grid gap-4 lg:grid-cols-2">
                {[...grouped.active, ...grouped.closed].map((goal) => (
                  <GoalCard
                    key={goal.id}
                    goal={goal}
                    onEdit={() => setEditingGoal(goal)}
                    onDelete={() => removeGoal.mutate(goal.id)}
                  />
                ))}
              </Reveal>
            )}

            <Reveal>
              <Card title="Tasks" subtitle="One-off things, unlike habits"
                    icon={ListTodo} accent="learning">
                <div className="flex flex-col gap-2">
                  <div className="flex gap-2">
                    <input
                      value={taskDraft}
                      onChange={(event) => setTaskDraft(event.target.value)}
                      onKeyDown={(event) => event.key === 'Enter' && addTask()}
                      placeholder="Add a task"
                      aria-label="Add a task"
                      className="min-w-0 flex-1 rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
                    />
                    <Button size="md" variant="secondary" icon={Plus}
                            className="shrink-0" onClick={addTask}
                            loading={saveTask.isPending}>
                      Add
                    </Button>
                  </div>

                  {data.tasks.length === 0 ? (
                    <p className="text-label text-ink-subtle">Nothing on the list.</p>
                  ) : (
                    data.tasks.map((task) => (
                      <TaskRow
                        key={task.id}
                        task={task}
                        onToggle={() => saveTask.mutate({
                          id: task.id, completed: !task.completed_on,
                        })}
                        onDelete={() => removeTask.mutate(task.id)}
                      />
                    ))
                  )}
                </div>
              </Card>
            </Reveal>

            <Reveal>
              <Card
                title="Habits"
                subtitle="Your daily checklist, with real schedules"
                icon={Repeat}
                accent="discipline"
              >
                <QueryBoundary query={habits} loading={<SkeletonGrid />}>
                  {(loaded) => (
                    <div className="flex flex-col gap-4">
                      <p className="flex items-start gap-1.5 text-caption text-ink-subtle">
                        <CheckCircle2 size={12} className="mt-0.5 shrink-0" aria-hidden />
                        Adherence and streaks are over the last {loaded.window_days} days.
                        A habit set to certain days is only expected on those days —
                        Today shows what is actually due.
                      </p>

                      <div className="grid gap-2 sm:grid-cols-2">
                        {loaded.habits.map((habit) => (
                          <HabitRow key={habit.id} habit={habit}
                                    onEdit={() => setEditingHabit(habit)} />
                        ))}
                      </div>
                    </div>
                  )}
                </QueryBoundary>
              </Card>
            </Reveal>
          </RevealGroup>
        )}
      </QueryBoundary>

      {editingGoal !== undefined && (
        <GoalEditor
          key={editingGoal?.id ?? 'new'}
          open
          goal={editingGoal}
          habits={summary.data?.habits ?? []}
          onClose={() => setEditingGoal(undefined)}
        />
      )}

      {editingHabit && (
        <HabitScheduler
          key={editingHabit.id}
          open
          habit={editingHabit}
          onClose={() => setEditingHabit(null)}
        />
      )}
    </>
  )
}
