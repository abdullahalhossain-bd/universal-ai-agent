// Thin fetch wrapper. In dev, Vite proxies /v1/* to the FastAPI backend; in prod, set VITE_API_BASE_URL to the deployed API origin at build time.
const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const TOKEN_KEY = 'merchant_console_token'
const ADMIN_TOKEN_KEY = 'platform_admin_token'
const CSRF_COOKIE = 'ucai_merchant_csrf'

export function getToken() { return localStorage.getItem(TOKEN_KEY) }
export function setToken(token) { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY) }
export function getAdminToken() { return localStorage.getItem(ADMIN_TOKEN_KEY) }
export function setAdminToken(token) { if (token) localStorage.setItem(ADMIN_TOKEN_KEY, token); else localStorage.removeItem(ADMIN_TOKEN_KEY) }

export class ApiError extends Error {
  constructor(status, detail, code = null, field = null) {
    const message = typeof detail === 'string' ? detail : detail?.message || 'Request failed'
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
    this.code = code || (detail && typeof detail === 'object' ? detail.error : null)
    this.field = field || (detail && typeof detail === 'object' ? detail.field : null)
  }
}

function getCookie(name) {
  const prefix = `${name}=`
  return document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(prefix))?.slice(prefix.length) || ''
}

function parseErrorDetail(data, status) {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = data.detail
    if (Array.isArray(detail)) {
      return detail.map(item => item?.msg || item?.message || String(item)).join('; ')
    }
    if (detail && typeof detail === 'object') return detail
    return detail
  }
  if (typeof data === 'string' && data.trim()) return data
  return `Request failed (${status})`
}

async function request(path, { method = 'GET', body, auth = true, headers = {}, token = null, timeoutMs = 20000 } = {}) {
  const finalHeaders = { ...headers }
  const normalizedMethod = method.toUpperCase()
  if (body !== undefined) finalHeaders['Content-Type'] = 'application/json'
  if (auth) {
    const resolvedToken = token ?? getToken()
    if (resolvedToken) finalHeaders['Authorization'] = `Bearer ${resolvedToken}`
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(normalizedMethod)) {
    const csrf = getCookie(CSRF_COOKIE)
    if (csrf) finalHeaders['x-csrf-token'] = decodeURIComponent(csrf)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), Math.max(1000, timeoutMs))
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: normalizedMethod,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw new ApiError(408, 'The request timed out. Please try again.')
    throw new ApiError(0, 'Unable to reach the API. Please check your connection and try again.')
  } finally {
    clearTimeout(timer)
  }

  let data = null
  const text = await res.text()
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }
  if (!res.ok) {
    throw new ApiError(res.status, parseErrorDetail(data, res.status))
  }
  return data
}

export const api = {
  get: (path, opts) => request(path, { ...opts, method: 'GET' }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body }),
  put: (path, body, opts) => request(path, { ...opts, method: 'PUT', body }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body }),
  del: (path, opts) => request(path, { ...opts, method: 'DELETE' }),
}

export const adminApi = {
  get: (path, opts) => request(path, { ...opts, method: 'GET', token: getAdminToken() }),
  post: (path, body, opts) => request(path, { ...opts, method: 'POST', body, token: getAdminToken() }),
  patch: (path, body, opts) => request(path, { ...opts, method: 'PATCH', body, token: getAdminToken() }),
}
