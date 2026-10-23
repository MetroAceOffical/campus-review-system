export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) { super(message) }
}
let expired: () => void = () => {}
export function onSessionExpired(callback: () => void) { expired = callback }
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const method = (options.method ?? 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = await request<{ headerName: string; token: string }>('/api/auth/csrf')
    headers.set(token.headerName, token.token)
  }
  if (typeof options.body === 'string') headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin', signal: options.signal ?? AbortSignal.timeout(options.body instanceof FormData ? 60000 : 15000) })
  const body = await response.json().catch(() => ({ code: 'INVALID_RESPONSE', message: '服务返回异常，请稍后重试' }))
  if (!response.ok || body.code !== 'OK') {
    if (response.status === 401 && path !== '/api/auth/login') expired()
    throw new ApiError(response.status, body.code, body.message ?? '操作未完成', body.details)
  }
  return body.data as T
}
