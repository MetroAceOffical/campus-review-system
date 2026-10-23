import { afterEach, describe, expect, it, vi } from 'vitest'
import { request, onSessionExpired } from '../src/api/http'

afterEach(() => { vi.unstubAllGlobals() })
describe('session-aware requests', () => {
  it('fetches a CSRF token before a write and sends cookies', async () => {
    const calls: Array<[string, RequestInit]> = []
    vi.stubGlobal('fetch', async (path: string, options: RequestInit) => {
      calls.push([path, options])
      if (path === '/api/auth/csrf') return new Response(JSON.stringify({ code: 'OK', data: { headerName: 'X-CSRF-TOKEN', token: 'fresh-token' } }))
      return new Response(JSON.stringify({ code: 'OK', data: { saved: true } }))
    })
    expect(await request('/api/manuscripts', { method: 'POST', body: '{}' })).toEqual({ saved: true })
    expect(calls[1][1].credentials).toBe('same-origin')
    expect(new Headers(calls[1][1].headers).get('X-CSRF-TOKEN')).toBe('fresh-token')
  })
  it('notifies reauthentication on 401 without replaying the write', async () => {
    let writes = 0
    const expired = vi.fn()
    onSessionExpired(expired)
    vi.stubGlobal('fetch', async (path: string) => {
      if (path === '/api/auth/csrf') return new Response(JSON.stringify({ code: 'OK', data: { headerName: 'X-CSRF-TOKEN', token: 'token' } }))
      writes++
      return new Response(JSON.stringify({ code: 'SESSION_EXPIRED', message: '请重新登录' }), { status: 401 })
    })
    await expect(request('/api/manuscripts/1/draft', { method: 'PUT', body: '{}' })).rejects.toMatchObject({ status: 401 })
    expect(expired).toHaveBeenCalledOnce()
    expect(writes).toBe(1)
  })
})
