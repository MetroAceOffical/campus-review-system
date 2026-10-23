import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import ReferenceListView from '../src/views/ReferenceListView.vue'
const { api } = vi.hoisted(() => ({ api: vi.fn() }))
vi.mock('../src/api/http', () => ({ request: api }))
afterEach(() => { vi.restoreAllMocks(); api.mockReset() })
it('keeps partial usability distinct from requested disable until the generation switch completes', async () => {
  const row = { referenceId: '1', revisionId: '1', title: '分项测试参考', originType: 'MANUAL', requestedEnabled: true, effectiveEnabled: true, processingStatus: 'PARTIAL', parts: { BODY: { status: 'AVAILABLE' }, 'OCR:image': { status: 'FAILED', errorCode: 'OCR_SERVICE_UNAVAILABLE' } }, sourceMetadata: { sourceType: 'MANUAL', description: '测试材料' }, createdAt: '2026-10-23T01:00:00Z', createdByName: '测试管理员', originalPublishedAt: null }
  api.mockImplementation(async (_path: string, options?: RequestInit) => { if (options?.method === 'PATCH') { row.requestedEnabled = false; return { requestedEnabled: false, effectiveEnabled: true, status: 'PENDING_SWITCH' } }; return { items: [structuredClone(row)], page: 1, pageSize: 20, total: 1, activeGenerationId: '1', latestGeneration: { generationId: '1', status: 'ACTIVE' } } })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
  const wrapper = mount(ReferenceListView, { global: { plugins: [ElementPlus], stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
  try {
    await flushPromises(); expect(wrapper.text()).toContain('部分可用'); expect(wrapper.text()).toContain('当前可检索')
    await wrapper.findAll('button').find(button => button.text() === '停用')!.trigger('click'); await flushPromises(); expect(wrapper.text()).toContain('停用待切换'); expect(wrapper.text()).toContain('当前可检索')
    row.effectiveEnabled = false
    await wrapper.findAll('button').find(button => button.text() === '刷新')!.trigger('click'); await flushPromises(); expect(wrapper.text()).toContain('当前不参与检索'); expect(wrapper.text()).not.toContain('停用待切换')
  } finally { wrapper.unmount() }
})
