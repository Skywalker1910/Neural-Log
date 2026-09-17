/**
 * Thin fetch wrapper over the Flask API.
 *
 * Auth is the existing Flask signed-cookie session - in dev Vite proxies /api to
 * Flask so the browser still sees one origin and cookies just work. The one
 * wrinkle: Flask's @login_required *redirects* to /login rather than returning
 * 401, and fetch follows redirects transparently, so an expired session shows up
 * as a 200 full of HTML. handleResponse detects that explicitly.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /**
     * The parsed error body, when the server sent one.
     *
     * Kept because a 400 often carries more than a sentence: onboarding returns
     * `fields` naming which answers were rejected, and throwing that away leaves
     * the UI able to say "something was wrong" and nothing else.
     */
    public body?: Record<string, unknown>,
  ) {
    super(message)
    this.name = 'ApiError'
  }

  /** Per-field validation messages, or an empty object when there were none. */
  get fields(): Record<string, string> {
    const fields = this.body?.fields
    return fields && typeof fields === 'object'
      ? (fields as Record<string, string>)
      : {}
  }
}

const LOGIN_URL = '/login'

function redirectToLogin(): never {
  window.location.href = LOGIN_URL
  throw new ApiError(401, 'Session expired - redirecting to sign in.')
}

async function handleResponse<T>(res: Response): Promise<T> {
  // Session expired: Flask bounced us to the Jinja login page.
  if (res.redirected && new URL(res.url).pathname.startsWith(LOGIN_URL)) {
    redirectToLogin()
  }

  if (res.status === 401 || res.status === 403) {
    redirectToLogin()
  }

  const contentType = res.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new ApiError(res.status, `Expected JSON from ${res.url} but got "${contentType}".`)
  }

  const body = (await res.json()) as T & { message?: string; error?: string }

  if (!res.ok) {
    throw new ApiError(
      res.status,
      body.message ?? body.error ?? `Request failed (${res.status}).`,
      body as Record<string, unknown>,
    )
  }

  return body
}

/**
 * The CSRF token the server handed us, read back out of its cookie.
 *
 * Double-submit: the server sets `csrf_token`, we echo it in a header, and it
 * checks the two match. That proves the request came from a page on this origin,
 * because a page on another origin can make your browser *send* cookies but
 * cannot *read* them to copy one into a header.
 *
 * Read fresh on every request rather than cached at module load. The cookie is
 * rotated when the server decides to, and a stale copy fails every write until
 * the tab is reloaded - which is exactly the bug that looks like "the app
 * randomly stopped saving".
 */
function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

const UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method ?? 'GET'

  let res: Response
  try {
    res = await fetch(path, {
      credentials: 'same-origin',
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(UNSAFE.test(method) ? { 'X-CSRF-Token': csrfToken() } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError(0, 'Could not reach the server. Check your connection and retry.')
  }
  return handleResponse<T>(res)
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body === undefined ? undefined : JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}
