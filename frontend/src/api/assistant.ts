import { ApiError } from './client'

/**
 * Talking to the assistant, which is the one endpoint that streams.
 *
 * `EventSource` is the obvious tool for server-sent events and it only does GET,
 * so it cannot carry a message body or the CSRF header. This reads the stream
 * off `fetch` instead - slightly more code, and it keeps the endpoint a POST
 * that goes through the same CSRF guard as every other write.
 */

export type AssistantEvent =
  | { type: 'status'; tool: string | null; writes: boolean; note?: string }
  | { type: 'done'; reply: string; queued: ProposedAction[]; budget: Budget }
  | { type: 'proposal'; id: number; actions: ProposedAction[] }
  | { type: 'input_card'; card: AssistantInputCard }
  | { type: 'error'; kind: string; message: string }
  | { type: 'end' }

/**
 * One queued change, as the server described it.
 *
 * Deliberately loose. The card renders `summary`, which the server wrote, and
 * only the editable numbers are reached into by name - so adding a new action
 * type on the server does not require a matching release of this file to avoid
 * rendering blank.
 */
export interface ProposedAction {
  type: string
  summary: string
  date?: string
  meal?: string
  items?: { food_id: number; name: string; grams: number }[]
  bedtime?: string | null
  wake_time?: string | null
  duration_minutes?: number | null
  quality?: number | null
  water_ml?: number | null
  steps?: number | null
  mood?: number | null
  topic?: string
  [key: string]: unknown
}

export interface AssistantInputField {
  id: string
  label: string
  type: 'time' | 'text' | 'number' | 'select'
  placeholder?: string
  options?: string[]
}

export interface AssistantInputCard {
  id: string
  topic: string
  eyebrow: string
  title: string
  prompt: string
  reason: string
  fields: AssistantInputField[]
  choices?: { label: string; message: string }[]
  submit_label: string
  message: string
}

export interface Budget {
  month_spent_usd: number
  month_budget_usd: number
  month_calls: number
  day_spent_usd: number
  day_budget_usd: number
  remaining_usd: number
}

export interface AssistantState {
  configured: boolean
  model: string
  budget: Budget
  pending_proposal: { id: number; actions: ProposedAction[]; created_at: string } | null
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

/**
 * Send a message and yield each event as the server emits it.
 *
 * An async generator rather than a callback because the caller wants to react
 * differently to each kind - a status event moves a label, a proposal opens a
 * card - and a `for await` loop reads as the sequence it is.
 */
export async function* streamChat(
  message: string,
  options: { kind?: 'general' | 'today'; date?: string; signal?: AbortSignal } = {},
): AsyncGenerator<AssistantEvent> {
  let response: Response
  try {
    response = await fetch('/api/assistant/chat', {
      method: 'POST',
      credentials: 'same-origin',
      signal: options.signal,
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
      body: JSON.stringify({ message, kind: options.kind ?? 'general', date: options.date }),
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }

  if (!response.ok || !response.body) {
    // A refusal arrives as ordinary JSON: the stream only starts once the
    // request is accepted.
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, body?.error ?? body?.message ?? 'The assistant could not start.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    // Events are separated by a blank line, and a chunk boundary can land
    // anywhere - including mid-event. Whatever is after the last separator is
    // incomplete and waits for the next read.
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      const line = part.split('\n').find((candidate) => candidate.startsWith('data: '))
      if (!line) continue
      try {
        yield JSON.parse(line.slice(6)) as AssistantEvent
      } catch {
        // A malformed frame is not worth failing the conversation over.
      }
    }
  }
}

/**
 * What a scanned nutrition panel came back as.
 *
 * `conversion_note` and `unreadable` exist so the confirmation card can show its
 * working rather than a confident number - a per-serving panel scaled to per-100g
 * has been multiplied by something, and the person should be able to see what.
 */
export interface ScannedFood {
  name: string
  category: string
  unit: 'g' | 'ml'
  kcal_per_100g: number
  protein_per_100g: number
  carbs_per_100g: number
  fat_per_100g: number
  fibre_per_100g: number
  serving_name: string | null
  serving_grams: number | null
  conversion_note: string
  unreadable: string[]
  basis: string
}

/**
 * Send a photo of a nutrition panel and get back a food to confirm.
 *
 * Deliberately not through `api.post`: that sets `Content-Type: application/json`,
 * and a multipart body needs the browser to set it *with the boundary it
 * generated*. Setting it by hand produces a request the server cannot parse.
 */
export async function scanLabel(image: Blob): Promise<ScannedFood> {
  const body = new FormData()
  body.append('image', image, 'label.jpg')

  let response: Response
  try {
    response = await fetch('/api/assistant/label', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrfToken() },
      body,
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server.')
  }

  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    // 422 carries a refusal the person can act on - "retake with the column
    // headings visible" - rather than a generic failure.
    throw new ApiError(response.status, payload?.error ?? 'That scan did not work.')
  }
  return payload as ScannedFood
}
