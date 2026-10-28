import { reactive } from 'vue'
import { request } from './api/http'

export type Role = 'MEMBER' | 'REVIEWER' | 'ADMIN'
export interface User { userId: string; displayName: string; role: Role; organizations: Array<{ organizationId: string; name: string }> }
export const session = reactive({ user: null as User | null, loaded: false, expired: false })
export const home = (_role: Role) => '/home'
export async function loadSession() {
  try { session.user = await request<User>('/api/auth/me') } catch { session.user = null }
  session.loaded = true
}
export async function login(username: string, password: string) {
  session.user = await request<User>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
  session.loaded = true
  session.expired = false
  return session.user
}
export async function logout() {
  await request('/api/auth/logout', { method: 'POST' })
  session.user = null
  session.expired = false
}
