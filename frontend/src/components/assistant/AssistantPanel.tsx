import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Bot, CheckCircle2, Pencil, Send, Sparkles, X } from 'lucide-react'
import { AnimatePresence, m } from 'motion/react'

import { api } from '../../api/client'
import { onOpenAssistant, type OpenAssistantRequest } from '../../lib/assistantBus'
import {
  streamChat, type AssistantInputCard, type AssistantState, type ProposedAction,
} from '../../api/assistant'
import { useAssistantState } from '../../api/queries'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'
import { ProposalCard } from './ProposalCard'
import { InputCard } from './InputCard'

/**
 * The assistant, as a panel over whatever page you are on.
 *
 * Not a route, because the point is to log something without leaving what you
 * were doing. Not a modal either - a modal that covers the page you are asking
 * about is the wrong shape for "what did I eat today".
 *
 * ## Why the whole thing disappears when there is no API key
 *
 * `/api/assistant/state` reports `configured`. When it is false this renders
 * nothing at all - no button, no empty panel, no "coming soon". An instance
 * without a key is not a broken instance; it is the app as it was last week,
 * and every workspace the assistant can reach is reachable by hand.
 */

interface Turn {
  role: 'user' | 'assistant'
  text: string
}

/** What the status events look like to a person, rather than to a developer. */
const TOOL_LABELS: Record<string, string> = {
  get_day: 'checking what you logged',
  search_foods: 'looking up foods',
  get_survey_questions: 'reading your check-in',
  propose_meal: 'writing up the meal',
  propose_sleep: 'writing up your sleep',
  propose_lifestyle: 'noting that down',
  propose_study: 'writing up the session',
  get_checkin_plan: 'working out what is worth asking',
  propose_checkin: 'writing up your check-in',
  search_exercises: 'looking up exercises',
  propose_workout: 'writing up the session',
}

/** What opens a guided check-in. The person pressed a button that means this,
 *  so sending it as their first turn is honest rather than a puppet string. */
const CHECKIN_OPENER = "Let's run through today."

export function AssistantPanel({
  onClose,
  request,
}: {
  onClose: () => void
  request: OpenAssistantRequest
}) {
  const queryClient = useQueryClient()
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [proposal, setProposal] = useState<{ id: number; actions: ProposedAction[] } | null>(null)
  const [inputCard, setInputCard] = useState<AssistantInputCard | null>(null)
  const [applied, setApplied] = useState<{ actions: ProposedAction[]; result: string[]; failed: string | null } | null>(null)
  const [savingProposal, setSavingProposal] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // A proposal left over from a previous visit. Somebody who closed the tab
  // mid-conversation should find their Save button where they left it.
  useEffect(() => {
    void api
      .get<AssistantState>('/api/assistant/state')
      .then((state) => {
        if (state.pending_proposal) {
          setProposal({ id: state.pending_proposal.id, actions: state.pending_proposal.actions })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // A check-in starts itself. Somebody who pressed "check in by chat" has
  // already said what they want; making them type "hello" first is friction for
  // its own sake.
  const started = useRef(false)
  useEffect(() => {
    if (request.kind !== 'today' || started.current) return
    started.current = true
    void send(CHECKIN_OPENER)
    // Once, on mount, for a check-in. `send` is recreated every render and
    // depending on it would re-fire the opener on each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request.kind])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, status, proposal, inputCard])

  async function send(override?: string, autoApply = true) {
    const message = (override ?? input).trim()
    if (!message || busy) return

    if (!override) setInput('')
    setError(null)
    setInputCard(null)
    setApplied(null)
    setTurns((current) => [...current, { role: 'user', text: message }])
    setBusy(true)
    setStatus('thinking')

    try {
      for await (const event of streamChat(message, {
        kind: request.kind,
        date: request.date,
        autoApply,
      })) {
        if (event.type === 'status') {
          setStatus(TOOL_LABELS[event.tool ?? ''] ?? 'working')
        } else if (event.type === 'done') {
          if (autoApply && event.queued.length > 0) continue
          setTurns((current) => [...current, { role: 'assistant', text: event.reply }])
        } else if (event.type === 'proposal') {
          setProposal({ id: event.id, actions: event.actions })
        } else if (event.type === 'input_card') {
          setInputCard(event.card)
        } else if (event.type === 'applied') {
          setApplied({ actions: event.actions, result: event.applied, failed: event.failed })
          void queryClient.invalidateQueries()
        } else if (event.type === 'error') {
          setError(event.message)
        }
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Something went wrong.')
    } finally {
      setBusy(false)
      setStatus(null)
    }
  }

  async function resolveProposal(accept: boolean, actions?: ProposedAction[]) {
    if (!proposal) return
    setSavingProposal(true)
    setError(null)
    try {
      const path = `/api/assistant/proposals/${proposal.id}/${accept ? 'apply' : 'discard'}`
      const result = await api.post<{ success: boolean; failed?: string | null }>(
        path,
        accept ? { actions } : {},
      )
      if (accept && result.failed) {
        setError(`Partly saved. ${result.failed}`)
      }
      setProposal(null)
      if (accept) {
        // A saved meal moves macros, attribute scores, XP and the streak, so
        // everything cached is now potentially stale. Broad on purpose: this
        // happens once per conversation, not per keystroke.
        await queryClient.invalidateQueries()
        setTurns((current) => [...current, { role: 'assistant', text: 'Saved.' }])
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save that.')
    } finally {
      setSavingProposal(false)
    }
  }

  return (
    <m.aside
      initial={{ x: '100%' }}
      animate={{ x: 0 }}
      exit={{ x: '100%' }}
      transition={{ type: 'spring', stiffness: 380, damping: 38 }}
      role="dialog"
      aria-label="Assistant"
      className={cn(
        'material-chrome fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line',
        'bg-surface-base sm:max-w-md',
      )}
    >
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
        <span className="flex min-w-0 items-center gap-2">
          <Bot size={18} className="shrink-0 text-brand" aria-hidden />
          <span className="truncate text-label font-semibold text-ink">
            {request.kind === 'today' ? 'Daily check-in' : 'Assistant'}
          </span>
        </span>
        <Button variant="ghost" size="sm" icon={X} onClick={onClose} aria-label="Close assistant" />
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {turns.length === 0 && !proposal && request.kind !== 'today' && (
          <div className="rounded-lg border border-line bg-surface-card p-4">
            <p className="text-label text-ink">Tell me about your day.</p>
            <p className="mt-1 text-meta text-ink-subtle">
              &ldquo;Two eggs and toast for breakfast&rdquo;, &ldquo;slept 11:30 to 6:45&rdquo;,
              &ldquo;studied ML for an hour&rdquo;. I&rsquo;ll write it up and you decide whether
              to save it.
            </p>
          </div>
        )}

        {turns.map((message, index) => (
          <div
            key={index}
            className={cn(
              'max-w-[85%] rounded-lg px-3 py-2 text-label',
              message.role === 'user'
                ? 'ml-auto bg-brand/15 text-ink'
                : 'mr-auto bg-surface-card text-ink',
            )}
          >
            {message.text}
          </div>
        ))}

        {status && (
          <p className="flex items-center gap-2 text-meta text-ink-subtle">
            <Sparkles size={14} className="animate-pulse" aria-hidden />
            {status}…
          </p>
        )}

        {proposal && (
          <ProposalCard
            /*
              Remounted whenever the queued set changes, which resets the
              editable draft inside.

              ProposalCard seeds that draft with `useState(() => ...)`, and an
              initialiser runs once - so without this, a check-in that queues
              sleep on one turn and training on the next kept rendering the
              first card forever while the server accumulated behind it. The
              person saves what looks right and loses the rest.

              The cost is that an edit in progress is discarded when a new turn
              queues something. That is the correct way round: the newest
              conversation is the better information, and a lost edit is visible
              where a missing action is not.
            */
            key={`${proposal.id}:${proposal.actions.length}`}
            actions={proposal.actions}
            saving={savingProposal}
            error={error}
            onSave={(actions) => void resolveProposal(true, actions)}
            onDiscard={() => void resolveProposal(false)}
          />
        )}

        {applied && (
          <section className="mr-auto max-w-[94%] rounded-xl border border-success/35 bg-success/10 p-3">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2 text-label font-semibold text-ink">
                <CheckCircle2 size={16} className="text-success" aria-hidden /> Changes added
              </span>
              <Button size="sm" variant="secondary" icon={Pencil} onClick={() => {
                setInput(`I need to correct: ${applied.actions.map((action) => action.summary).join('; ')}`)
                inputRef.current?.focus()
              }}>
                Edit
              </Button>
            </div>
            <ul className="mt-2 space-y-1 text-meta text-ink-muted">
              {applied.actions.map((action, index) => <li key={index}>{action.summary}</li>)}
            </ul>
            {applied.failed && <p className="mt-2 text-meta text-danger">Partly added: {applied.failed}</p>}
          </section>
        )}

        {inputCard && !proposal && (
          <InputCard card={inputCard} disabled={busy} onSend={(message, autoApply) => void send(message, autoApply)} />
        )}

        {error && !proposal && <p className="text-label text-danger">{error}</p>}
      </div>

      <form
        className="flex shrink-0 items-center gap-2 border-t border-line px-4 py-3"
        onSubmit={(event) => {
          event.preventDefault()
          void send()
        }}
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="What did you have for lunch?"
          aria-label="Message the assistant"
          maxLength={2000}
          className={cn(
            'min-w-0 flex-1 rounded-md border border-line bg-surface-card px-3 py-2',
            'text-label text-ink outline-none transition-colors focus:border-brand',
          )}
        />
        <Button type="submit" variant="primary" size="sm" icon={Send} loading={busy}
                disabled={!input.trim()} aria-label="Send" />
      </form>
    </m.aside>
  )
}

/**
 * The button, and the panel it opens.
 *
 * Renders nothing when the instance has no API key - see the file docstring.
 */
export function AssistantLauncher() {
  const [request, setRequest] = useState<OpenAssistantRequest | null>(null)
  const assistant = useAssistantState()

  // Today's "check in by chat" button fires this. Subscribed unconditionally:
  // hooks cannot be called after an early return, and it costs nothing.
  useEffect(() => onOpenAssistant(setRequest), [])

  if (!assistant.data?.configured) return null

  return (
    <>
      {!request && (
        <button
          type="button"
          onClick={() => setRequest({ kind: 'general' })}
          aria-label="Open the assistant"
          className={cn(
            'fixed bottom-20 right-4 z-40 flex size-12 items-center justify-center rounded-full lg:bottom-6',
            'border border-line bg-surface-raised text-brand shadow-lg',
            'transition-transform duration-200 ease-apple hover:scale-105',
          )}
        >
          <Bot size={22} aria-hidden />
        </button>
      )}

      <AnimatePresence>
        {request && (
          <AssistantPanel
            // Keyed by mode: switching from free chat to a check-in should
            // start a fresh panel, not carry the old transcript into it.
            key={request.kind}
            request={request}
            onClose={() => setRequest(null)}
          />
        )}
      </AnimatePresence>
    </>
  )
}
