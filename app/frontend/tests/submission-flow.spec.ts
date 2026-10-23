import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import EditorView from '../src/views/EditorView.vue'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/http', () => ({ request: api }))
const EditorStub = defineComponent({ name: 'CampusEditor', emits: ['uploading', 'uploadError'], template: '<div />' })
afterEach(() => { vi.restoreAllMocks(); api.mockReset() })
it('blocks submission during uploads, retains failed edits, and retries an ambiguous submission with the same key', async () => {
  const draft = { manuscriptId: '1', organizationId: '1', status: 'DRAFT', revision: '0', title: '原稿', schemaVersion: '1', content: { type: 'doc', content: [] }, sources: [], savedAt: '2026-10-23T01:00:00Z' }
  const submissions: RequestInit[] = []
  api.mockImplementation(async (path: string, options?: RequestInit) => {
    if(path==='/api/settings/limits')return {titleCodePoints:200,bodyCodePoints:10000,images:6,imageBytes:10485760,imagePixels:20000000,imageSide:8000,urlCharacters:2000}
    if (options?.method === 'PUT') throw new Error('保存网络失败')
    if (path.endsWith('/submissions') && options?.method === 'POST') { submissions.push(options); throw new Error('请求结果暂不确定，请重试') }
    return draft
  })
  // Element Plus declares an input-data intersection for confirm; its runtime resolves the action string.
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/manuscripts/:id/edit', component: EditorView }] })
  await router.push('/manuscripts/1/edit'); await router.isReady()
  const wrapper = mount(EditorView, { global: { plugins: [ElementPlus, router], stubs: { CampusEditor: EditorStub } } })
  try {
    await flushPromises(); await wrapper.get('input[aria-label="稿件标题"]').setValue('尚未保存的新标题')
    const save = wrapper.findAll('button').find(button => button.text() === '保存草稿')!
    await save.trigger('click'); await flushPromises(); expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value', '尚未保存的新标题')
    const submit = () => wrapper.findAll('button').find(button => button.text() === '送审')!
    expect(submit()).toBeDefined()
    wrapper.getComponent(EditorStub).vm.$emit('uploading', true); await flushPromises(); expect(submit().attributes('disabled')).toBeDefined()
    wrapper.getComponent(EditorStub).vm.$emit('uploading', false); wrapper.getComponent(EditorStub).vm.$emit('uploadError', true); await flushPromises(); expect(submit().attributes('disabled')).toBeDefined()
    wrapper.getComponent(EditorStub).vm.$emit('uploadError', false); await flushPromises()
    await submit().trigger('click'); await flushPromises(); await submit().trigger('click'); await flushPromises()
    expect(submissions).toHaveLength(2); expect(new Headers(submissions[0]!.headers).get('Idempotency-Key')).toBe(new Headers(submissions[1]!.headers).get('Idempotency-Key'))
    expect(JSON.parse(String(submissions[0]!.body)).title).toBe('尚未保存的新标题')
    expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value', '尚未保存的新标题')
  } finally { wrapper.unmount() }
})
