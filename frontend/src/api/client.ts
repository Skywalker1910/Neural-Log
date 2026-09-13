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
  ) {
    super(message)
    this.name = 'ApiError'
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
    throw new ApiError(res.status, body.message ?? body.error ?? `Request failed (${res.status}).`)
  }

  return body
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      credentials: 'same-origin',
      ...init,
      headers: {
        'Content-Type': 'application/json',
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
