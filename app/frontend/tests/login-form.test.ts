import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import LoginForm from '../src/components/LoginForm.vue'

afterEach(() => vi.unstubAllGlobals())
it('prevents native credential submission and sends login only in a POST body', async () => {
  const calls: Array<{ path: string; options: RequestInit }> = []
  vi.stubGlobal('fetch', async (path: string, options: RequestInit) => {
    calls.push({ path, options })
    return new Response(JSON.stringify({ code: 'OK', data: path.endsWith('/csrf') ? { headerName: 'X-CSRF-TOKEN', token: 'test-token' } : { userId: '1', displayName: '成员', role: 'MEMBER', organizations: [] } }))
  })
  const wrapper = mount(LoginForm, { global: { plugins: [ElementPlus] } })
  try {
    await wrapper.get('input[name="username"]').setValue('member-test')
    await wrapper.get('input[name="password"]').setValue('fixture-password')
    expect(wrapper.findAll('form')).toHaveLength(1)
    const event = new Event('submit', { cancelable: true, bubbles: true })
    wrapper.get('form').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    await flushPromises()
    expect(calls.find(call => call.path === '/api/auth/login')?.options.method).toBe('POST')
    expect(calls.every(call => !call.path.includes('password'))).toBe(true)
  } finally { wrapper.unmount() }
})
