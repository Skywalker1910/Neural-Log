import { useState } from 'react'

import type { LearningArea, LearningTopic } from '../../api/types'
import { useSaveArea, useSaveTopic } from '../../api/queries'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { cn } from '../../lib/cn'
import { accentBg, accentText, type Accent } from '../../navigation'

/** The design system's accents, reused so an area never invents its own colour. */
const ACCENTS: Accent[] = [
  'learning', 'brand', 'fitness', 'lifestyle', 'goals', 'discipline', 'recovery',
]

const STATUSES: LearningTopic['status'][] = ['active', 'paused', 'done']

interface AreaEditorProps {
  open: boolean
  onClose: () => void
  /** Null creates a new area; an area edits it in place. */
  area: LearningArea | null
}

export function AreaEditor({ open, onClose, area }: AreaEditorProps) {
  const save = useSaveArea()

  const [name, setName] = useState(area?.name ?? '')
  const [accent, setAccent] = useState<string>(area?.accent ?? 'learning')
  const [target, setTarget] = useState(
    area?.weekly_target_minutes != null ? String(area.weekly_target_minutes) : '',
  )

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    save.mutate(
      {
        id: area?.id,
        name: name.trim(),
        accent,
        weekly_target_minutes: target === '' ? null : Number(target),
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={area ? 'Edit area' : 'New area'}
      description="An area is a domain you are learning. Topics live inside it."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Name</span>
          <input
            value={name} required autoFocus
            onChange={(event) => setName(event.target.value)}
            placeholder="Computer Science"
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <div>
          <span className="mb-1 block text-meta text-ink-muted">Colour</span>
          <div className="flex flex-wrap gap-2">
            {ACCENTS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setAccent(option)}
                aria-pressed={accent === option}
                aria-label={option}
                className={cn(
                  'size-8 rounded-full border-2 transition-transform',
                  accentBg[option],
                  accent === option
                    ? 'scale-110 border-ink'
                    : 'border-transparent hover:scale-105',
                )}
              >
                <span className={cn('text-caption font-bold', accentText[option])}>
                  {accent === option ? '●' : ''}
                </span>
              </button>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">
            Weekly target (minutes) — optional
          </span>
          <input
            type="number" min="0" inputMode="numeric" value={target}
            onChange={(event) => setTarget(event.target.value)}
            placeholder="leave blank to use your overall target"
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
          />
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {area ? 'Save area' : 'Create area'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}

interface TopicEditorProps {
  open: boolean
  onClose: () => void
  topic: LearningTopic | null
  areas: LearningArea[]
}

export function TopicEditor({ open, onClose, topic, areas }: TopicEditorProps) {
  const save = useSaveTopic()

  const [name, setName] = useState(topic?.name ?? '')
  const [areaId, setAreaId] = useState(topic?.area_id ? String(topic.area_id) : '')
  const [status, setStatus] = useState<LearningTopic['status']>(topic?.status ?? 'active')
  const [notes, setNotes] = useState(topic?.notes ?? '')

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim()) return
    save.mutate(
      {
        id: topic?.id,
        name: name.trim(),
        area_id: areaId === '' ? null : Number(areaId),
        status,
        notes: notes.trim() || null,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={topic ? 'Edit topic' : 'New topic'}
      description="What you actually sit down and study."
    >
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Name</span>
          <input
            value={name} required autoFocus
            onChange={(event) => setName(event.target.value)}
            placeholder="Distributed Systems"
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Area</span>
          <select
            value={areaId}
            onChange={(event) => setAreaId(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          >
            <option value="">Unfiled</option>
            {areas.map((area) => (
              <option key={area.id} value={area.id}>{area.name}</option>
            ))}
          </select>
        </label>

        <div>
          <span className="mb-1 block text-meta text-ink-muted">Status</span>
          <div className="flex gap-1.5">
            {STATUSES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setStatus(option)}
                aria-pressed={status === option}
                className={cn(
                  'flex-1 rounded-md border px-3 py-1.5 text-meta capitalize transition-colors',
                  status === option
                    ? 'border-learning bg-learning/15 text-learning'
                    : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
                )}
              >
                {option}
              </button>
            ))}
          </div>
          <p className="mt-1 text-caption text-ink-subtle">
            A finished topic keeps its history — it just stops cluttering the
            session picker.
          </p>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Notes</span>
          <textarea
            value={notes} rows={2}
            onChange={(event) => setNotes(event.target.value)}
            className="w-full resize-y rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          />
        </label>

        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>
            {topic ? 'Save topic' : 'Create topic'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
