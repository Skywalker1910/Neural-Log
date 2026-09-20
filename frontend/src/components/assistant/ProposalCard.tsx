import { useState } from 'react'
import { Check, Pencil, X } from 'lucide-react'

import type { ProposedAction } from '../../api/assistant'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'

/**
 * The card that turns a conversation into a save.
 *
 * Everything the assistant wants to write shows up here first, once, with one
 * Save button - not a confirmation per field, which would make talking slower
 * than typing and defeat the point.
 *
 * ## Why the numbers are editable
 *
 * Because the mistakes are numeric. The assistant rarely invents a meal you did
 * not eat; it mishears eighty grams as eight hundred, or forty-five minutes as
 * thirty-five. Making those correctable here saves a whole round of
 * conversation, and it is the difference between the card being a speed bump and
 * being useful.
 *
 * The server will not accept a change of *shape* - the action types and their
 * order are checked against what was proposed. So this form can only ever adjust
 * what a save means, never what it does.
 */

interface ProposalCardProps {
  actions: ProposedAction[]
  saving?: boolean
  error?: string | null
  onSave: (actions: ProposedAction[]) => void
  onDiscard: () => void
}

/** Which values a person is allowed to correct, per action type. */
const EDITABLE: Record<string, { key: string; label: string; suffix?: string }[]> = {
  sleep: [
    { key: 'bedtime', label: 'To bed' },
    { key: 'wake_time', label: 'Woke' },
    { key: 'quality', label: 'Quality', suffix: '/5' },
  ],
  lifestyle: [
    { key: 'water_ml', label: 'Water', suffix: 'ml' },
    { key: 'steps', label: 'Steps' },
    { key: 'mood', label: 'Mood', suffix: '/5' },
  ],
  study: [{ key: 'duration_minutes', label: 'Minutes' }],
}

function Value({
  label,
  suffix,
  value,
  onChange,
}: {
  label: string
  suffix?: string
  value: string
  onChange: (next: string) => void
}) {
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-caption uppercase tracking-wide text-ink-subtle">{label}</span>
      <span className="flex items-baseline gap-1">
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={cn(
            'tabular w-full min-w-0 rounded-md border border-line bg-surface-base px-2 py-1',
            'text-label text-ink outline-none transition-colors focus:border-brand',
          )}
        />
        {suffix && <span className="shrink-0 text-meta text-ink-subtle">{suffix}</span>}
      </span>
    </label>
  )
}

export function ProposalCard({ actions, saving, error, onSave, onDiscard }: ProposalCardProps) {
  const [draft, setDraft] = useState<ProposedAction[]>(() =>
    actions.map((action) => ({ ...action, items: action.items?.map((item) => ({ ...item })) })),
  )
  const [editing, setEditing] = useState(false)

  const update = (index: number, key: string, raw: string) => {
    setDraft((current) =>
      current.map((action, position) =>
        position === index
          ? { ...action, [key]: raw === '' ? null : /^-?\d+(\.\d+)?$/.test(raw) ? Number(raw) : raw }
          : action,
      ),
    )
  }

  const updateItem = (index: number, itemIndex: number, grams: string) => {
    setDraft((current) =>
      current.map((action, position) =>
        position === index
          ? {
              ...action,
              items: action.items?.map((item, spot) =>
                spot === itemIndex ? { ...item, grams: Number(grams) || 0 } : item,
              ),
            }
          : action,
      ),
    )
  }

  return (
    <div className="rounded-lg border border-brand/40 bg-brand/[0.06] p-4">
      <p className="text-label font-semibold text-ink">Ready to save</p>
      <p className="mt-0.5 text-meta text-ink-subtle">
        Nothing has been written yet. Check it over first.
      </p>

      <ul className="mt-3 flex flex-col gap-3">
        {draft.map((action, index) => (
          <li key={index} className="min-w-0 rounded-md border border-line bg-surface-card p-3">
            <p className="text-label text-ink">{action.summary}</p>

            {editing && action.items && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {action.items.map((item, itemIndex) => (
                  <Value
                    key={itemIndex}
                    label={item.name}
                    suffix="g"
                    value={String(item.grams ?? '')}
                    onChange={(next) => updateItem(index, itemIndex, next)}
                  />
                ))}
              </div>
            )}

            {editing && EDITABLE[action.type] && (
              <div className="mt-3 grid gap-3 sm:grid-cols-3">
                {EDITABLE[action.type].map((field) => (
                  <Value
                    key={field.key}
                    label={field.label}
                    suffix={field.suffix}
                    value={action[field.key] == null ? '' : String(action[field.key])}
                    onChange={(next) => update(index, field.key, next)}
                  />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>

      {error && <p className="mt-3 text-label text-danger">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" size="sm" icon={Check} loading={saving} onClick={() => onSave(draft)}>
          Save
        </Button>
        <Button
          variant="secondary"
          size="sm"
          icon={Pencil}
          onClick={() => setEditing((open) => !open)}
        >
          {editing ? 'Done editing' : 'Edit'}
        </Button>
        <Button variant="ghost" size="sm" icon={X} onClick={onDiscard} disabled={saving}>
          Discard
        </Button>
      </div>
    </div>
  )
}
