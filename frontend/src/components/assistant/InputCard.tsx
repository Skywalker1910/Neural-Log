import { useState } from 'react'
import { ArrowUpRight, CircleDot, Sparkles } from 'lucide-react'
import { m } from 'motion/react'

import type { AssistantInputCard } from '../../api/assistant'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'

/** A compact form that answers the next guided-check-in question. */
export function InputCard({
  card,
  disabled,
  onSend,
}: {
  card: AssistantInputCard
  disabled: boolean
  onSend: (message: string) => void
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [sent, setSent] = useState(false)
  const complete = card.fields.every((field) => values[field.id]?.trim())

  function submit() {
    if (!complete || disabled || sent) return
    setSent(true)
    onSend(card.message.replace(/\{(\w+)\}/g, (_, key: string) => values[key]?.trim() ?? ''))
  }

  function choose(message: string) {
    if (disabled || sent) return
    setSent(true)
    onSend(message)
  }

  return (
    <m.section
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 360, damping: 28 }}
      className={cn(
        'relative mr-auto max-w-[94%] overflow-hidden rounded-xl border border-brand/30',
        'bg-gradient-to-br from-brand-muted via-surface-card to-surface-raised p-3 shadow-raised',
        sent && 'opacity-60',
      )}
    >
      <div className="pointer-events-none absolute -right-8 -top-8 size-28 rounded-full bg-brand/20 blur-2xl" />
      <div className="relative">
        <div className="mb-3 flex items-start justify-between gap-3">
          <span>
            <span className="flex items-center gap-1.5 text-caption uppercase tracking-[0.14em] text-brand-hover">
              <Sparkles size={12} aria-hidden /> {card.eyebrow}
            </span>
            <h3 className="mt-1 text-section text-ink">{card.title}</h3>
          </span>
          <span className="flex size-8 items-center justify-center rounded-full border border-brand/30 bg-brand/10 text-brand-hover">
            <CircleDot size={15} aria-hidden />
          </span>
        </div>

        <p className="text-meta text-ink-muted">{card.prompt}</p>
        <p className="mt-1 text-caption text-ink-subtle">Why now: {card.reason}</p>

        <div className="mt-3 grid gap-2">
          {card.fields.map((field) => (
            <label key={field.id} className="grid gap-1 text-caption uppercase tracking-wide text-ink-subtle">
              {field.label}
              {field.type === 'select' ? (
                <select
                  value={values[field.id] ?? ''}
                  disabled={disabled || sent}
                  onChange={(event) => setValues((current) => ({ ...current, [field.id]: event.target.value }))}
                  className="rounded-md border border-line-strong bg-surface-base/80 px-2.5 py-2 text-label normal-case tracking-normal text-ink outline-none focus:border-brand"
                >
                  <option value="">Choose one</option>
                  {field.options?.map((option) => <option key={option} value={option.toLowerCase()}>{option}</option>)}
                </select>
              ) : (
                <input
                  type={field.type}
                  inputMode={field.type === 'number' ? 'numeric' : undefined}
                  placeholder={field.placeholder}
                  value={values[field.id] ?? ''}
                  disabled={disabled || sent}
                  onChange={(event) => setValues((current) => ({ ...current, [field.id]: event.target.value }))}
                  className="rounded-md border border-line-strong bg-surface-base/80 px-2.5 py-2 text-label normal-case tracking-normal text-ink outline-none placeholder:text-ink-subtle focus:border-brand"
                />
              )}
            </label>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="primary" icon={ArrowUpRight} disabled={!complete || disabled || sent}
                  onClick={submit}>
            {sent ? 'Added to chat' : card.submit_label}
          </Button>
          {card.choices?.map((choice) => (
            <Button key={choice.label} size="sm" variant="secondary" disabled={disabled || sent}
                    onClick={() => choose(choice.message)}>
              {choice.label}
            </Button>
          ))}
        </div>
      </div>
    </m.section>
  )
}
