/**
 * Opening the assistant from somewhere that is not the assistant.
 *
 * The launcher lives in the app shell and the Today page wants to open it in
 * check-in mode. Threading a callback down through the router to do that means
 * every page between them carries a prop it does not use, and a context provider
 * means a re-render of the whole tree whenever the panel opens.
 *
 * A window event is the smaller thing. The coupling is one-directional and
 * stringly-typed in exactly one place - here - and a page that fires it does not
 * need to know whether anything is listening, which is right: on an instance
 * with no API key, nothing is.
 */

const EVENT = 'neurallog:open-assistant'

export interface OpenAssistantRequest {
  /** 'today' runs the guided check-in; 'general' is free chat. */
  kind: 'general' | 'today'
  /** The day being discussed, for a check-in. Defaults to today on the server. */
  date?: string
}

export function openAssistant(request: OpenAssistantRequest): void {
  window.dispatchEvent(new CustomEvent<OpenAssistantRequest>(EVENT, { detail: request }))
}

/** Returns the unsubscribe function, for an effect cleanup. */
export function onOpenAssistant(handler: (request: OpenAssistantRequest) => void): () => void {
  const listener = (event: Event) => handler((event as CustomEvent<OpenAssistantRequest>).detail)
  window.addEventListener(EVENT, listener)
  return () => window.removeEventListener(EVENT, listener)
}
