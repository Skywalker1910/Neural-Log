import { useCallback, useEffect, useState } from 'react'
import { m } from 'motion/react'
import { Info, Play, Square } from 'lucide-react'

import type { LearningTopic } from '../../api/types'
import { useLogSession } from '../../api/queries'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { cn } from '../../lib/cn'
import { isoDate, todayISO } from '../../lib/date'
import { spring } from '../../lib/motion'

const STORAGE_KEY = 'neurallog:study-timer'

function clock(date: Date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function hms(totalSeconds: number) {
  const seconds = Math.max(0, totalSeconds)
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

interface Stored {
  startedAt: number
  topicId: number | null
}

function readStored(): Stored | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Stored
    return typeof parsed?.startedAt === 'number' ? parsed : null
  } catch {
    // Private windows and blocked site data both throw here. A timer that cannot
    // be remembered is a degraded feature, not a broken page.
    return null
  }
}

function writeStored(value: Stored | null) {
  try {
    if (value) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    else window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* see readStored */
  }
}

interface SessionLoggerProps {
  open: boolean
  onClose: () => void
  topics: LearningTopic[]
  /** Pre-selects a topic when opened from a topic row. */
  topicId?: number | null
}

/**
 * Start a study session, or write one down after the fact.
 *
 * The running timer is driven by a stored start TIMESTAMP rather than a ticking
 * counter, and the timestamp lives in localStorage. Both matter: browsers
 * throttle timers in background tabs, and studying is precisely the activity
 * during which you will switch away from this tab for an hour. Comparing against
 * a stored start means the timer is right the moment you look back at it, and
 * survives a reload.
 *
 * Start and end times are recorded alongside the duration because they are what
 * let two sessions fifteen minutes apart count as one interrupted block rather
 * than two short ones - see docs/LEARNING.md.
 */
export function SessionLogger({ open, onClose, topics, topicId }: SessionLoggerProps) {
  const log = useLogSession()

  const [stored, setStored] = useState<Stored | null>(readStored)
  const [elapsed, setElapsed] = useState(0)

  const [topic, setTopic] = useState<string>(topicId ? String(topicId) : '')
  const [date, setDate] = useState(todayISO)
  const [minutes, setMinutes] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [focus, setFocus] = useState<number | null>(null)
  const [difficulty, setDifficulty] = useState<number | null>(null)
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (!stored) return

    // Closes over `stored`, which is this effect's only dependency, so the
    // interval always reads the start time it was created for.
    const tick = () => setElapsed(Math.floor((Date.now() - stored.startedAt) / 1000))
    tick()
    const id = window.setInterval(tick, 1000)
    return () => window.clearInterval(id)
  }, [stored])

  const start = useCallback(() => {
    const value: Stored = {
      startedAt: Date.now(),
      topicId: topic ? Number(topic) : null,
    }
    writeStored(value)
    setStored(value)
  }, [topic])

  const stop = useCallback(() => {
    if (!stored) return
    const began = new Date(stored.startedAt)
    const ended = new Date()

    setDate(isoDate(began))
    setStartTime(clock(began))
    setEndTime(clock(ended))
    setMinutes(String(Math.max(1, Math.round((ended.getTime() - began.getTime()) / 60000))))
    if (stored.topicId) setTopic(String(stored.topicId))

    writeStored(null)
    setStored(null)
    setElapsed(0)
  }, [stored])

  function discard() {
    writeStored(null)
    setStored(null)
    setElapsed(0)
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    const duration = Number(minutes)
    if (!duration || duration <= 0) return

    log.mutate(
      {
        date,
        topic_id: topic ? Number(topic) : null,
        duration_minutes: duration,
        started_at: startTime || null,
        ended_at: endTime || null,
        focus_rating: focus,
        difficulty,
        notes: notes.trim() || null,
      },
      {
        onSuccess: () => {
          setMinutes('')
          setStartTime('')
          setEndTime('')
          setNotes('')
          setFocus(null)
          setDifficulty(null)
          onClose()
        },
      },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Study session"
      description="Start a timer, or write down a session you have already done."
      size="md"
    >
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-meta text-ink-muted">Topic</span>
          <select
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            className="rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
          >
            <option value="">Unfiled</option>
            {topics.filter((t) => t.status !== 'done').map((option) => (
              <option key={option.id} value={option.id}>
                {option.area_name ? `${option.area_name} · ${option.name}` : option.name}
              </option>
            ))}
          </select>
        </label>

        {/* --- the running timer --- */}
        <div
          className={cn(
            'flex items-center gap-3 rounded-md border p-3',
            stored ? 'border-learning/50 bg-learning/10' : 'border-line bg-surface-base',
          )}
        >
          <span className="tabular flex-1 text-metric text-ink" aria-live="polite">
            {stored ? hms(elapsed) : '0:00'}
          </span>
          {stored ? (
            <>
              <Button size="sm" variant="ghost" onClick={discard}>Discard</Button>
              <Button size="sm" variant="primary" icon={Square} onClick={stop}>
                Stop
              </Button>
            </>
          ) : (
            <Button size="sm" variant="secondary" icon={Play} onClick={start}>
              Start timer
            </Button>
          )}
        </div>

        {stored && (
          <p className="flex items-start gap-1.5 text-caption text-ink-subtle">
            <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
            Keeps running if you close this or switch tabs — it counts from the
            moment you started, not from this window being open.
          </p>
        )}

        {/* --- the form --- */}
        <form onSubmit={submit} className="flex flex-col gap-3 border-t border-line pt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
              <span className="text-meta text-ink-muted">Date</span>
              <input
                type="date" value={date} max={todayISO()}
                onChange={(event) => setDate(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">Minutes</span>
              <input
                type="number" min="1" inputMode="numeric" value={minutes} required
                onChange={(event) => setMinutes(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-3 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">From</span>
              <input
                type="time" value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-2 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-meta text-ink-muted">To</span>
              <input
                type="time" value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
                className="rounded-md border border-line bg-surface-base px-2 py-2 text-label tabular text-ink outline-none focus:border-brand"
              />
            </label>
          </div>

          <p className="text-caption text-ink-subtle">
            Times are optional, but they let sessions close together count as one
            block — which is what Focus actually measures.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            <Scale label="Focus" value={focus} onChange={setFocus}
                   low="scattered" high="locked in" />
            <Scale label="Difficulty" value={difficulty} onChange={setDifficulty}
                   low="easy" high="hard" />
          </div>

          <div className="flex items-start gap-2">
            <Badge tone="neutral" className="shrink-0 whitespace-nowrap">not scored</Badge>
            <p className="text-caption text-ink-subtle">
              Both are for your own reference. Focus as an attribute is measured
              from how long your uninterrupted blocks were, not from how focused
              you felt — otherwise the app would just be paying you to rate
              yourself a five.
            </p>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-meta text-ink-muted">Notes</span>
            <textarea
              value={notes} rows={2}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="What did you actually cover?"
              className="w-full resize-y rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none focus:border-brand"
            />
          </label>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" variant="primary" loading={log.isPending}>
              Log session
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  )
}

function Scale({
  label, value, onChange, low, high,
}: {
  label: string
  value: number | null
  onChange: (next: number) => void
  low: string
  high: string
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-meta text-ink-muted">{label}</span>
        <span className="text-caption text-ink-subtle">{low} → {high}</span>
      </div>
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((option) => (
          <m.button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            aria-pressed={value === option}
            aria-label={`${label}: ${option} of 5`}
            whileTap={{ scale: 0.94 }}
            transition={spring.snappy}
            className={cn(
              'flex h-8 flex-1 items-center justify-center rounded-md border tabular text-label transition-colors',
              value === option
                ? 'border-learning bg-learning/15 text-learning'
                : 'border-line text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            {option}
          </m.button>
        ))}
      </div>
    </div>
  )
}
