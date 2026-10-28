import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, it, vi } from 'vitest'
import DatasetView from '../src/views/DatasetView.vue'

function versionedFixture(rowLoader?: (page: number) => Promise<unknown>) {
  const base = { invalidRows: 0, missing: { text: 0, title: 0 }, completeness: { text: 1 }, issueCounts: {}, lengths: {}, sourceDistribution: {}, departmentDistribution: {}, dateDistribution: {}, classDistribution: {} }
  const before = { ...base, totalRows: 31, validRows: 31, duplicateRows: 1 }, after = { ...base, totalRows: 30, validRows: 30, duplicateRows: 0 }
  const rawRun = { runId: 'raw-run', inputVersionId: 'raw-1', outputVersionId: '', action: 'AUDIT', status: 'COMPLETED', mapping: {}, result: { audit: before, columns: ['正文', '标题'], mapping: { text: '正文', title: '标题' }, preview: [{ title: '原始样本', text: '原始正文' }] } }
  const cleanRun = { runId: 'clean-run', inputVersionId: 'raw-1', outputVersionId: 'clean-1', action: 'CLEAN', status: 'COMPLETED', mapping: { text: '正文', title: '标题' }, result: { outputRows: 30 } }
  const data = { datasetId: 'versioned', name: '多版本数据', kind: 'NEWS', organizationId: '1', archived: false, versions: [{ versionId: 'clean-1', stage: 'CLEAN', status: 'READY', rowCount: 30 }, { versionId: 'raw-1', stage: 'RAW', status: 'READY', rowCount: 31 }], runs: [cleanRun, rawRun] }
  route.query.dataset = 'versioned'
  api.mockImplementation((path: string, options?: RequestInit) => {
    if (path.endsWith('/organizations')) return Promise.resolve([{ organizationId: '1', name: '新闻中心' }])
    if (path.includes('/datasets?')) return Promise.resolve({ items: [data], total: 1 })
    if (path === '/api/workbench/datasets/versioned') return Promise.resolve(data)
    if (options?.method === 'POST') return Promise.resolve({ runId: 'new-task' })
    if (path.endsWith('/report')) return Promise.resolve({ before, after, inputRows: 31, outputRows: 30, duplicateRows: 1 })
    if (path.includes('/rows?')) { const page = Number(new URL(path, 'http://localhost').searchParams.get('page')); return rowLoader ? rowLoader(page) : Promise.resolve({ total: 30, items: [{ title: '清洗样本', text: '清洗正文' }] }) }
    if (path.includes('/events')) return Promise.resolve([])
    return Promise.reject(new Error(path))
  })
}

const { api, route, replace } = vi.hoisted(() => ({ api: vi.fn(), route: { query: {} as Record<string, string> }, replace: vi.fn().mockResolvedValue(undefined) }))
vi.mock('../src/api/http', () => ({ request: api }))
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ replace }) }))
afterEach(() => { api.mockReset(); route.query = {}; replace.mockClear(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('shows actionable load failure instead of empty success', async () => {
  api.mockRejectedValue(new Error('数据中心暂不可用'))
  const wrapper = mount(DatasetView, { global: { plugins: [ElementPlus], stubs: { DatasetCharts: true } } })
  await flushPromises()
  expect(wrapper.text()).toContain('数据中心暂不可用')
  expect(wrapper.text()).toContain('重试')
  wrapper.unmount()
})

it('renders actual audit numbers and an independent cleaning action', async () => {
  route.query.dataset = 'dataset-1'
  const audit = { totalRows: 3021, validRows: 3000, invalidRows: 21, duplicateRows: 4, missing: {}, completeness: {}, issueCounts: {}, lengths: {}, sourceDistribution: {}, departmentDistribution: {}, dateDistribution: {}, classDistribution: {} }
  const run = { runId: 'run-1', datasetId: 'dataset-1', action: 'AUDIT', status: 'COMPLETED', inputVersionId: 'raw-1', outputVersionId: '', error: '', result: { audit, columns: ['正文'], preview: [{ text: '真实新闻正文' }] } }
  api.mockImplementation((path: string) => {
    if (path === '/api/workbench/organizations') return Promise.resolve([{ organizationId: '1', name: '校新闻中心' }])
    if (path.startsWith('/api/workbench/datasets?')) return Promise.resolve({ total: 1, items: [{ datasetId: 'dataset-1', name: '新闻中心历史稿', kind: 'NEWS', organizationId: '1', archived: false }] })
    if (path === '/api/workbench/datasets/dataset-1') return Promise.resolve({ datasetId: 'dataset-1', name: '新闻中心历史稿', kind: 'NEWS', organizationId: '1', versions: [{ versionId: 'raw-1', stage: 'RAW', status: 'READY', rowCount: 3021 }], runs: [run] })
    if (path === '/api/workbench/runs/run-1') return Promise.resolve(run)
    if (path.includes('/events')) return Promise.resolve([])
    return Promise.reject(new Error(`Unexpected request: ${path}`))
  })
  const wrapper = mount(DatasetView, { global: { plugins: [ElementPlus], stubs: { DatasetCharts: true } } })
  await flushPromises()
  const choose = wrapper.findAll('button').find(button => button.text().includes('新闻中心历史稿'))
  expect(choose).toBeTruthy()
  expect(wrapper.text()).toContain('3,021')
  expect(wrapper.text()).toContain('3,000')
  expect(wrapper.text()).toContain('21')
  expect(wrapper.text()).toContain('生成清洗版本')
  expect(wrapper.text()).toContain('真实新闻正文')
  expect(wrapper.text()).not.toContain('训练完成')
  wrapper.unmount()
})

it('ignores a disconnected old stream after switching datasets', async () => {
  class FakeEvents {
    static instances: FakeEvents[] = []
    onerror: (() => void) | null = null; closed = false
    constructor(_url: string) { FakeEvents.instances.push(this) }
    addEventListener() {}
    close() { this.closed = true }
  }
  vi.stubGlobal('EventSource', FakeEvents)
  const list = ['one', 'two'].map(id => ({ datasetId: id, name: `数据集${id}`, kind: 'NEWS', organizationId: '1', archived: false }))
  api.mockImplementation((path: string) => {
    if (path.endsWith('/organizations')) return Promise.resolve([{ organizationId: '1', name: '校新闻中心' }])
    if (path.includes('/datasets?')) return Promise.resolve({ total: 2, items: list })
    if (path.includes('/events')) return Promise.resolve([])
    const id = path.split('/').at(-1)!
    return Promise.resolve({ ...list.find(x => x.datasetId === id), versions: [{ versionId: `raw-${id}`, stage: 'RAW', status: 'READY' }], runs: [{ runId: `run-${id}`, datasetId: id, action: 'AUDIT', status: 'RUNNING', mapping: {} }] })
  })
  const wrapper = mount(DatasetView, { global: { plugins: [ElementPlus], stubs: { DatasetCharts: true } } })
  await flushPromises()
  await wrapper.findAll('button').find(x => x.text().includes('数据集one'))!.trigger('click'); await flushPromises()
  await wrapper.findAll('button').find(x => x.text().includes('数据集two'))!.trigger('click'); await flushPromises()
  FakeEvents.instances[0]!.onerror?.()
  expect(FakeEvents.instances[1]!.closed).toBe(false)
  wrapper.unmount(); vi.unstubAllGlobals()
})

it('binds mapping, quality and samples to the selected input version', async () => {
  versionedFixture()
  const wrapper = mount(DatasetView, { global: { plugins: [ElementPlus], stubs: { DatasetCharts: true } } })
  await flushPromises()
  expect(wrapper.find('.dataset-stats').text()).toContain('总记录30')
  expect(wrapper.text()).toContain('清洗样本')
  await wrapper.find('select[aria-label="输入版本"]').setValue('raw-1'); await flushPromises()
  expect(wrapper.find('.dataset-stats').text()).toContain('总记录31')
  expect(wrapper.text()).toContain('原始样本')
  await wrapper.find('select[aria-label="输入版本"]').setValue('clean-1'); await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '生成清洗版本')!.trigger('click'); await flushPromises()
  const post = api.mock.calls.find(([path, options]) => String(path).endsWith('/runs') && options?.method === 'POST')!
  expect(JSON.parse(post[1].body).versionId).toBe('clean-1')
  expect(JSON.parse(post[1].body).mapping).toEqual({})
  wrapper.unmount()
})

it('keeps the current sample page when an earlier page returns late', async () => {
  let finishSecond: ((value: unknown) => void) | undefined
  versionedFixture(page => page === 2 ? new Promise(resolve => { finishSecond = resolve }) : Promise.resolve({ total: 30, items: [{ title: `样本第${page}页`, text: '对应页面内容' }] }))
  const wrapper = mount(DatasetView, { global: { plugins: [ElementPlus], stubs: { DatasetCharts: true } } })
  await flushPromises()
  const next = () => wrapper.findAll('button').filter(button => button.attributes('aria-label') === 'Go to next page').at(-1)!
  await next().trigger('click'); await flushPromises()
  expect(finishSecond).toBeTruthy()
  await next().trigger('click'); await flushPromises()
  finishSecond!({ total: 30, items: [{ title: '样本第2页', text: '迟到的页面内容' }] }); await flushPromises()
  expect(wrapper.text()).toContain('样本第3页')
  expect(wrapper.text()).not.toContain('样本第2页')
  wrapper.unmount()
})
