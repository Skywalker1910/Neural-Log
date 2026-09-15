import { useMemo, useState } from 'react'
import { AnimatePresence, m } from 'motion/react'
import {
  CalendarCheck,
  Check,
  ChevronLeft,
  ChevronRight,
  PartyPopper,
  X,
} from 'lucide-react'

import type { Badge as BadgeType, ChecklistItem } from '../api/types'
import { useChecklistItems, useDay, useSaveDay } from '../api/queries'
import { PageHeader } from '../components/layout/PageHeader'
import { AnimatedNumber } from '../components/ui/AnimatedNumber'
import { ItemIcon } from '../components/ui/ItemIcon'
import { iconForItem } from '../lib/itemIcons'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ProgressRing } from '../components/ui/ProgressRing'
import { QueryBoundary } from '../components/ui/QueryBoundary'
import { Reveal, RevealGroup } from '../components/ui/Reveal'
import { SkeletonGrid } from '../components/ui/Skeleton'
import { cn } from '../lib/cn'
import { shiftISO, todayISO } from '../lib/date'
import { scaleIn, slideIn, spring } from '../lib/motion'

function humanDate(iso: string, today: string): string {
  if (iso === today) return 'Today'
  if (iso === shiftISO(today, -1)) return 'Yesterday'
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

/** How much of an item's weight a given answer earns. Mirrors item_credit() in
 *  scoring/engine.py so the progress ring matches what the server will score. */
function creditFor(item: ChecklistItem, answer: string | undefined): number {
  if (!answer) return 0
  if (item.type === 'rating') return 0
  if (item.type === 'yes-no') return answer.toLowerCase().startsWith('yes') ? 1 : 0
  if (item.type === 'time') {
    const index = (item.options ?? []).indexOf(answer)
    const ladder = [1, 0.8, 0.55, 0.3]
    if (index < 0) return 0.5
    return ladder[index] ?? ladder[ladder.length - 1]
  }
  return 1
}

interface ItemRowProps {
  item: ChecklistItem
  answer: string | undefined
  onAnswer: (value: string) => void
}

function ItemRow({ item, answer, onAnswer }: ItemRowProps) {
  const answered = Boolean(answer)
  const earned = creditFor(item, answer)

  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-md border p-4 transition-colors sm:flex-row sm:items-center sm:gap-4',
        answered ? 'border-line-strong bg-surface-raised' : 'border-line bg-surface-card',
      )}
    >
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <ItemIcon name={iconForItem(item.icon, item.name)} size={40} />
        <div className="min-w-0">
          <p className="text-label text-ink">{item.name}</p>
          {item.weight > 1 && (
            <span className="text-caption uppercase text-ink-subtle">
              weight {item.weight}
            </span>
          )}
        </div>
        <AnimatePresence>
          {earned > 0 && (
            <m.span
              className="ml-auto shrink-0 text-success sm:ml-0"
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              transition={spring.snappy}
            >
              <Check size={18} aria-label="completed" />
            </m.span>
          )}
        </AnimatePresence>
      </div>

      <div className="shrink-0">
        {item.type === 'yes-no' && (
          <div className="flex gap-2">
            {[
              { value: 'No', icon: X },
              { value: 'Yes', icon: Check },
            ].map((option) => (
              <Choice
                key={option.value}
                selected={answer === option.value}
                onClick={() => onAnswer(option.value)}
                tone={option.value === 'Yes' ? 'positive' : 'neutral'}
              >
                {option.value}
              </Choice>
            ))}
          </div>
        )}

        {item.type === 'time' && (
          <div className="flex flex-wrap gap-2">
            {(item.options ?? []).map((option) => (
              <Choice key={option} selected={answer === option} onClick={() => onAnswer(option)}>
                {option}
              </Choice>
            ))}
          </div>
        )}

        {item.type === 'rating' && (
          <div className="flex gap-2">
            {['1', '2', '3', '4', '5'].map((value) => (
              <Choice key={value} selected={answer === value} onClick={() => onAnswer(value)}>
                {value}
              </Choice>
            ))}
          </div>
        )}

        {item.type === 'text' && (
          <input
            type="text"
            value={answer ?? ''}
            onChange={(event) => onAnswer(event.target.value)}
            placeholder="Your answer"
            className="w-full rounded-md border border-line bg-surface-base px-3 py-2 text-label text-ink outline-none transition-colors focus:border-brand sm:w-64"
          />
        )}
      </div>
    </div>
  )
}

function Choice({
  selected,
  onClick,
  children,
  tone = 'neutral',
}: {
  selected: boolean
  onClick: () => void
  children: React.ReactNode
  tone?: 'neutral' | 'positive'
}) {
  return (
    <m.button
      type="button"
      onClick={onClick}
      whileTap={{ scale: 0.94 }}
      transition={spring.snappy}
      aria-pressed={selected}
      className={cn(
        'rounded-md border px-3 py-2 text-label transition-colors',
        selected
          ? tone === 'positive'
            ? 'border-success bg-success/15 text-success'
            : 'border-brand bg-brand/15 text-ink'
          : 'border-line bg-surface-base text-ink-muted hover:border-line-strong hover:text-ink',
      )}
    >
      {children}
    </m.button>
  )
}

function BadgeCelebration({ badges, onDismiss }: { badges: BadgeType[]; onDismiss: () => void }) {
  return (
    <AnimatePresence>
      {badges.length > 0 && (
        <m.div
          className="fixed inset-x-4 bottom-24 z-50 mx-auto max-w-md lg:bottom-8"
          initial={{ opacity: 0, y: 24, scale: 0.96 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.98 }}
          transition={spring.soft}
        >
          <div className="rounded-lg border border-discipline/40 bg-surface-overlay p-4 shadow-overlay">
            <div className="flex items-start gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-discipline/15 text-discipline">
                <PartyPopper size={20} aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-label font-semibold text-ink">
                  {badges.length === 1 ? 'Badge unlocked' : `${badges.length} badges unlocked`}
                </p>
                {badges.map((badge) => (
                  <p key={badge.code} className="text-meta text-ink-muted">
                    <span className="text-ink">{badge.name}</span> — {badge.description}
                  </p>
                ))}
              </div>
              <Button size="sm" variant="ghost" onClick={onDismiss}>
                Dismiss
              </Button>
            </div>
          </div>
        </m.div>
      )}
    </AnimatePresence>
  )
}

export function Today() {
  const today = todayISO()
  const [date, setDate] = useState(today)
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [editingDate, setEditingDate] = useState(date)
  const [celebrating, setCelebrating] = useState<BadgeType[]>([])

  const itemsQuery = useChecklistItems()
  const dayQuery = useDay(date)
  const save = useSaveDay(date)

  const items = useMemo(() => itemsQuery.data?.items ?? [], [itemsQuery.data])

  // Whatever is already logged for this date, straight from the server.
  const savedAnswers = useMemo(() => {
    const existing: Record<string, string> = {}
    for (const item of dayQuery.data?.items ?? []) {
      if (item.response) existing[item.name] = item.response
    }
    return existing
  }, [dayQuery.data])

  // Unsaved edits layered over the saved answers, rather than copied into state
  // by an effect. Deriving avoids a stale-copy bug when the query refetches, and
  // means an in-flight edit is never clobbered by a background refresh.
  const answers = useMemo(
    () => ({ ...savedAnswers, ...edits }),
    [savedAnswers, edits],
  )

  // Switching day discards edits. Adjusting state during render is React's own
  // recommendation for "reset when a prop changes" - an effect would render the
  // previous day's answers once before correcting itself.
  if (editingDate !== date) {
    setEditingDate(date)
    setEdits({})
  }

  const { completion, answered } = useMemo(() => {
    let total = 0
    let earned = 0
    let count = 0
    for (const item of items) {
      if (item.type === 'rating') continue
      total += item.weight
      earned += item.weight * creditFor(item, answers[item.name])
      if (answers[item.name]) count += 1
    }
    return {
      completion: total ? Math.round((earned / total) * 100) : 0,
      answered: count,
    }
  }, [items, answers])

  const scorable = items.filter((item) => item.type !== 'rating').length
  const ratingItem = items.find((item) => item.type === 'rating')

  function handleSave() {
    save.mutate(
      {
        responses: answers,
        self_rating: ratingItem ? Number(answers[ratingItem.name]) || undefined : undefined,
      },
      {
        onSuccess: (result) => {
          if (result.newly_earned_badges.length > 0) {
            setCelebrating(result.newly_earned_badges)
          }
        },
      },
    )
  }

  return (
    <>
      <PageHeader
        title={humanDate(date, today)}
        description={date === today ? 'What did the day actually look like?' : date}
        icon={CalendarCheck}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              icon={ChevronLeft}
              onClick={() => setDate((value) => shiftISO(value, -1))}
              aria-label="Previous day"
            />
            <Button
              size="sm"
              icon={ChevronRight}
              onClick={() => setDate((value) => shiftISO(value, 1))}
              disabled={date >= today}
              aria-label="Next day"
            />
          </div>
        }
      />

      <QueryBoundary query={itemsQuery} loading={<SkeletonGrid />}>
        {() => (
          <RevealGroup className="flex flex-col gap-4" step={0.05}>
            <Reveal>
              <Card bodyClassName="flex flex-wrap items-center gap-6">
                <ProgressRing
                  value={completion}
                  size={104}
                  accent="lifestyle"
                  ariaLabel={`${completion}% complete`}
                  label={
                    <AnimatedNumber
                      value={completion}
                      suffix="%"
                      className="tabular text-section font-bold text-lifestyle"
                    />
                  }
                />
                {/*
                  A min width rather than min-w-0: flex-wrap only moves whole
                  items to the next line, so with no floor this block shrank to
                  a sliver instead of pushing the button down - "9 / 9" broke
                  across two lines and the badge became a vertical stripe.
                */}
                <div className="min-w-[11rem] flex-1">
                  <p className="tabular text-metric text-ink">
                    <AnimatedNumber value={answered} />
                    <span className="text-section text-ink-subtle"> / {scorable}</span>
                  </p>
                  <p className="text-label text-ink-muted">questions answered</p>
                  {dayQuery.data?.logged && (
                    <Badge className="mt-2" tone="success">
                      Already logged — saving again corrects it
                    </Badge>
                  )}
                </div>
                <Button
                  variant="primary"
                  onClick={handleSave}
                  loading={save.isPending}
                  disabled={answered === 0}
                >
                  {dayQuery.data?.logged ? 'Update day' : 'Save day'}
                </Button>
              </Card>
            </Reveal>

            {save.isError && (
              <Reveal>
                <Card bodyClassName="text-label text-danger">
                  Could not save this day. Your answers are still here — try again.
                </Card>
              </Reveal>
            )}

            <RevealGroup className="flex flex-col gap-3" step={0.03}>
              {items.map((item) => (
                <Reveal key={item.id} variants={slideIn}>
                  <ItemRow
                    item={item}
                    answer={answers[item.name]}
                    onAnswer={(value) =>
                      setEdits((current) => ({ ...current, [item.name]: value }))
                    }
                  />
                </Reveal>
              ))}
            </RevealGroup>

            {save.isSuccess && !save.isPending && (
              <Reveal variants={scaleIn}>
                <p className="text-center text-meta text-ink-subtle">
                  Saved. Home and your attributes have been updated.
                </p>
              </Reveal>
            )}
          </RevealGroup>
        )}
      </QueryBoundary>

      <BadgeCelebration badges={celebrating} onDismiss={() => setCelebrating([])} />
    </>
  )
}
