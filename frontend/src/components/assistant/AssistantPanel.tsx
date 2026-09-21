import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Bot, Send, Sparkles, X } from 'lucide-react'
import { AnimatePresence, m } from 'motion/react'

import { api } from '../../api/client'
import { streamChat, type AssistantState, type ProposedAction } from '../../api/assistant'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'
import { ProposalCard } from './ProposalCard'

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
}

export function AssistantPanel({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [proposal, setProposal] = useState<{ id: number; actions: ProposedAction[] } | null>(null)
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

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, status, proposal])

  async function send() {
    const message = input.trim()
    if (!message || busy) return

    setInput('')
    setError(null)
    setTurns((current) => [...current, { role: 'user', text: message }])
    setBusy(true)
    setStatus('thinking')

    try {
      for await (const event of streamChat(message)) {
        if (event.type === 'status') {
          setStatus(TOOL_LABELS[event.tool ?? ''] ?? 'working')
        } else if (event.type === 'done') {
          setTurns((current) => [...current, { role: 'assistant', text: event.reply }])
        } else if (event.type === 'proposal') {
          setProposal({ id: event.id, actions: event.actions })
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
          <span className="truncate text-label font-semibold text-ink">Assistant</span>
        </span>
        <Button variant="ghost" size="sm" icon={X} onClick={onClose} aria-label="Close assistant" />
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {turns.length === 0 && !proposal && (
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
            actions={proposal.actions}
            saving={savingProposal}
            error={error}
            onSave={(actions) => void resolveProposal(true, actions)}
            onDiscard={() => void resolveProposal(false)}
          />
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
  const [open, setOpen] = useState(false)
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    void api
      .get<AssistantState>('/api/assistant/state')
      .then((state) => setAvailable(state.configured))
      .catch(() => setAvailable(false))
  }, [])

  if (!available) return null

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
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

      <AnimatePresence>{open && <AssistantPanel onClose={() => setOpen(false)} />}</AnimatePresence>
    </>
  )
}
