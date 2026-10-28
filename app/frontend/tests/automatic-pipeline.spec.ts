import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, expect, test, vi } from 'vitest'
import AutomaticPipeline from '../src/components/workbench/AutomaticPipeline.vue'
import type { Detail } from '../src/api/workbench'

const api = vi.hoisted(() => ({ pipelines: vi.fn(), startPipeline: vi.fn(), controlPipeline: vi.fn(), modelNames: { cnn: 'CNN' } }))
vi.mock('../src/api/training', () => api)
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

test('submits selected full parameters, polls persisted stages and stops on exit', async () => {
  vi.useFakeTimers(); api.pipelines.mockResolvedValue({ total: 0, items: [] }); api.startPipeline.mockResolvedValue({ pipelineId: 'pipeline' })
  const dataset: Detail = { datasetId: 'dataset', name: '新闻中心', kind: 'NEWS', archived: false, organizationId: '1', versions: [{ versionId: 'raw', stage: 'RAW', status: 'READY', sha256: 'a', rowCount: 3684 }], runs: [] }
  const parameters = { epochs: 8, batch_size: 16, device: 'cuda' }
  const wrapper = mount(AutomaticPipeline, { props: { dataset, versionId: 'raw', models: [{ family: 'cnn', parameters }], preparation: { ratios: [.8, .1, .1], seed: 42 }, generation: { max_originals: 0, variants: 2 }, name: '完整数据训练' }, global: { plugins: [ElementPlus], stubs: { RouterLink: true } } })
  try {
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '开始自动流程')!.trigger('click'); await flushPromises()
    expect(api.startPipeline).toHaveBeenCalledWith(expect.objectContaining({ versionId: 'raw', models: [{ family: 'cnn', parameters }], generation: { max_originals: 0, variants: 2 }, evaluate: true }))
    api.pipelines.mockResolvedValue({ total: 1, items: [{ pipelineId: 'pipeline', datasetId: 'dataset', name: '完整数据训练', status: 'RUNNING', state: { stage: 'CLEAN', currentRunId: 'clean-run', steps: [], models: [] } }] })
    const before = api.pipelines.mock.calls.length
    await vi.advanceTimersByTimeAsync(2500); await flushPromises(); expect(api.pipelines.mock.calls.length).toBe(before + 1)
    expect(wrapper.emitted('view')).toEqual([['clean-run']])
    api.pipelines.mockResolvedValue({ total: 1, items: [{ pipelineId: 'pipeline', datasetId: 'dataset', name: '完整数据训练', status: 'RUNNING', state: { stage: 'PREPARE', currentRunId: 'prepare-run', steps: [], models: [] } }] })
    await vi.advanceTimersByTimeAsync(2500); await flushPromises(); expect(wrapper.emitted('view')).toEqual([['clean-run'], ['prepare-run']])
    wrapper.unmount(); const ended = api.pipelines.mock.calls.length
    await vi.advanceTimersByTimeAsync(5000); expect(api.pipelines.mock.calls.length).toBe(ended)
  } finally { if (wrapper.exists()) wrapper.unmount() }
})
