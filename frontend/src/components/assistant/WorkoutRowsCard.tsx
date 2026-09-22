import { useMemo, useState } from 'react'
import { Check, Plus, Search, X } from 'lucide-react'
import { m } from 'motion/react'

import { api } from '../../api/client'
import type { AssistantInputCard, WorkoutRow, WorkoutSubmission } from '../../api/assistant'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'

/**
 * A training session, with the numbers a training session actually has.
 *
 * The card this replaces asked for "sets each", "reps each" and "weight each" —
 * one set of numbers for every exercise you ticked. That works for a circuit
 * that genuinely is 3×10 and is wrong for everything else, because nobody
 * benches and curls the same load. It recorded a number that was false for most
 * of the session, or you gave up and typed it out by hand.
 *
 * So every row carries its own. The rows arrive pre-filled from a saved
 * routine's targets, or empty from a muscle-group pick, and you correct what
 * differed.
 *
 * ## Why this submits structured data rather than a sentence
 *
 * Every other card answers by composing a sentence and sending it as an ordinary
 * chat turn — a good rule, and one this deliberately breaks. Six exercises with
 * their own numbers flatten into a paragraph that costs a round trip to write,
 * another to re-read, and throws away the exercise ids the card already looked
 * up. The server queues it through the same tool the model would have called, so
 * it is the same validation and the same confirmation card — just without
 * paying a model to re-read what we already knew.
 */

interface Draft extends WorkoutRow {
  selected: boolean
  sets: number | null
  reps: number | null
  weight: number | null
}

function Num({
  value,
  onChange,
  placeholder,
  ariaLabel,
  disabled,
}: {
  value: number | null
  onChange: (next: number | null) => void
  placeholder: string
  ariaLabel: string
  disabled?: boolean
}) {
  return (
    <input
      inputMode="decimal"
      aria-label={ariaLabel}
      placeholder={placeholder}
      disabled={disabled}
      value={value ?? ''}
      onChange={(event) => {
        const raw = event.target.value.trim()
        onChange(raw === '' ? null : Number(raw) || null)
      }}
      className={cn(
        'tabular w-full min-w-0 rounded-md border border-line bg-surface-base px-2 py-1.5',
        'text-label text-ink outline-none transition-colors focus:border-fitness',
        'disabled:opacity-40',
      )}
    />
  )
}

export function WorkoutRowsCard({
  card,
  disabled,
  onSubmit,
}: {
  card: AssistantInputCard
  disabled: boolean
  onSubmit: (message: string, structured: WorkoutSubmission) => void
}) {
  const [unit, setUnit] = useState<'kg' | 'lb'>(card.weight_unit === 'lb' ? 'lb' : 'kg')
  const [rows, setRows] = useState<Draft[]>(() =>
    (card.rows ?? []).map((row) => ({
      ...row,
      selected: Boolean(row.selected),
      sets: row.sets ?? null,
      reps: row.reps ?? null,
      weight: row.weight ?? null,
    })),
  )
  const [sent, setSent] = useState(false)
  const [adding, setAdding] = useState(false)
  const [query, setQuery] = useState('')
  const [found, setFound] = useState<WorkoutRow[]>([])

  const ready = useMemo(
    () => rows.some((row) => row.selected && row.sets),
    [rows],
  )

  function update(index: number, patch: Partial<Draft>) {
    setRows((current) => current.map((row, at) => (at === index ? { ...row, ...patch } : row)))
  }

  async function search() {
    const needle = query.trim()
    if (needle.length < 2) return
    try {
      const result = await api.get<{ exercises: { id: number; name: string; primary_muscle: string }[] }>(
        `/api/exercises?q=${encodeURIComponent(needle)}`,
      )
      setFound(
        result.exercises
          // Already on the card — adding it twice would log it twice.
          .filter((entry) => !rows.some((row) => row.exercise_id === entry.id))
          .slice(0, 8)
          .map((entry) => ({
            exercise_id: entry.id,
            name: entry.name,
            detail: entry.primary_muscle,
          })),
      )
    } catch {
      setFound([])
    }
  }

  function add(row: WorkoutRow) {
    setRows((current) => [...current, { ...row, selected: true, sets: null, reps: null, weight: null }])
    setQuery('')
    setFound([])
    setAdding(false)
  }

  function submit() {
    if (!ready || disabled || sent) return
    setSent(true)

    const chosen = rows.filter((row) => row.selected && row.sets)
    const described = chosen
      .map((row) =>
        `${row.name} ${row.sets}×${row.reps ?? '?'}` +
        (row.weight ? ` at ${row.weight}${unit}` : ''),
      )
      .join(', ')

    onSubmit(`I did ${card.title}: ${described}.`, {
      type: 'workout',
      name: card.title,
      weight_unit: unit,
      exercises: chosen.map((row) => ({
        exercise_id: row.exercise_id,
        name: row.name,
        sets: row.sets,
        reps: row.reps,
        weight: row.weight,
      })),
    })
  }

  return (
    <m.section
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className="min-w-0 rounded-lg border border-fitness/40 bg-fitness/[0.06] p-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="min-w-0">
          <span className="block text-caption uppercase tracking-wide text-ink-subtle">
            {card.eyebrow}
          </span>
          <span className="block text-label font-semibold text-ink">{card.title}</span>
        </span>

        {/* Per card, not per set. Somebody lifts in one unit on a given day, and
            a toggle on every row would be six decisions instead of none. */}
        <span className="flex shrink-0 overflow-hidden rounded-pill border border-line">
          {(['kg', 'lb'] as const).map((option) => (
            <button
              key={option}
              type="button"
              disabled={disabled || sent}
              onClick={() => setUnit(option)}
              className={cn(
                'px-2.5 py-0.5 text-meta transition-colors',
                unit === option ? 'bg-fitness/20 text-fitness' : 'text-ink-muted hover:text-ink',
              )}
            >
              {option}
            </button>
          ))}
        </span>
      </header>

      <p className="mt-1 text-meta text-ink-subtle">{card.prompt}</p>

      <ul className="mt-3 flex flex-col gap-2">
        {rows.map((row, index) => (
          <li
            key={`${row.exercise_id}-${index}`}
            className={cn(
              'min-w-0 rounded-md border p-2 transition-colors',
              row.selected ? 'border-line bg-surface-card' : 'border-line/60 bg-transparent',
            )}
          >
            <label className="flex min-w-0 items-start gap-2">
              <input
                type="checkbox"
                checked={row.selected}
                disabled={disabled || sent}
                onChange={(event) => update(index, { selected: event.target.checked })}
                className="mt-1 size-4 shrink-0 accent-[var(--color-fitness)]"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-label text-ink">{row.name}</span>
                {row.detail && (
                  <span className="block truncate text-caption text-ink-subtle">{row.detail}</span>
                )}
              </span>
            </label>

            {row.selected && (
              <div className="mt-2 grid grid-cols-3 gap-2 pl-6">
                <Num value={row.sets} onChange={(v) => update(index, { sets: v })}
                     placeholder="sets" ariaLabel={`${row.name} sets`} disabled={disabled || sent} />
                <Num value={row.reps} onChange={(v) => update(index, { reps: v })}
                     placeholder="reps" ariaLabel={`${row.name} reps`} disabled={disabled || sent} />
                <Num value={row.weight} onChange={(v) => update(index, { weight: v })}
                     placeholder={unit} ariaLabel={`${row.name} weight in ${unit}`}
                     disabled={disabled || sent} />
              </div>
            )}
          </li>
        ))}
      </ul>

      {/* Nobody follows a routine exactly. Without this you log the plan rather
          than the session. */}
      {card.allow_add && !sent && (
        <div className="mt-2">
          {adding ? (
            <div className="flex flex-col gap-2">
              <span className="flex gap-2">
                <input
                  autoFocus
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && void search()}
                  placeholder="Search the exercise library"
                  aria-label="Search exercises to add"
                  className="min-w-0 flex-1 rounded-md border border-line bg-surface-base px-2 py-1.5 text-label text-ink outline-none focus:border-fitness"
                />
                <Button size="sm" variant="secondary" icon={Search}
                        onClick={() => void search()} aria-label="Search" />
                <Button size="sm" variant="ghost" icon={X}
                        onClick={() => { setAdding(false); setFound([]) }} aria-label="Cancel" />
              </span>
              {found.map((entry) => (
                <button
                  key={entry.exercise_id}
                  type="button"
                  onClick={() => add(entry)}
                  className="rounded-md border border-line bg-surface-card px-2 py-1.5 text-left text-label text-ink hover:border-fitness/50"
                >
                  {entry.name}
                  <span className="ml-2 text-caption text-ink-subtle">{entry.detail}</span>
                </button>
              ))}
            </div>
          ) : (
            <Button size="sm" variant="ghost" icon={Plus} disabled={disabled}
                    onClick={() => setAdding(true)}>
              Add an exercise
            </Button>
          )}
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <Button variant="primary" size="sm" icon={Check}
                disabled={!ready || disabled || sent} onClick={submit}>
          {card.submit_label ?? 'Log session'}
        </Button>
        {!ready && (
          <span className="text-meta text-ink-subtle">Tick something and give it a set count.</span>
        )}
      </div>
    </m.section>
  )
}
