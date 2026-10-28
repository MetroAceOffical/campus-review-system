import { afterEach, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import FormalTrainingProgress from '../src/components/workbench/FormalTrainingProgress.vue'
import type { FormalProgress } from '../src/api/training'

const api = vi.hoisted(() => ({ formalProgress: vi.fn() }))
vi.mock('../src/api/training', () => api)
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

test('refreshes real counters, leaves pending model curves empty and stops polling on exit', async () => {
  vi.useFakeTimers()
  const response: FormalProgress = { observedAt: '2026-10-28T06:00:00Z', recipe: { generationOriginals: 3684, generationSegments: 16773, epochsBge: 2, epochsM3: 2 }, stages: [
    { key: 'generation', title: '样本准备', state: 'GENERATING_TRAIN_MATERIAL', availability: 'AVAILABLE', updatedAt: '2026-10-28T06:00:00Z', metrics: { accepted: 560, pending: 16168, quarantined: 45, reused: 440 }, latest: {}, history: [], progress: { processed: 605, total: 16773, percent: 3.6 } },
    { key: 'bge', title: '校园BGE检索训练', state: 'NOT_STARTED', availability: 'PENDING', metrics: {}, latest: {}, history: [] },
    { key: 'm3', title: 'M3内容对应训练', state: 'NOT_STARTED', availability: 'PENDING', metrics: {}, latest: {}, history: [] },
  ] }
  api.formalProgress.mockImplementation(async () => JSON.parse(JSON.stringify(response)))
  const wrapper = shallowMount(FormalTrainingProgress, { global: { stubs: Object.fromEntries(['el-button', 'el-descriptions', 'el-descriptions-item', 'el-table', 'el-table-column', 'el-tag', 'el-progress'].map(name => [name, true])) } })
  try {
    await flushPromises()
    expect(wrapper.text()).toContain('560')
    expect(wrapper.text()).toContain('未启动')
    expect(wrapper.findAllComponents({ name: 'ExperimentChart' }).map(c => c.props('title'))).toEqual(['实时样本准备数量'])
    response.stages[0]!.metrics.accepted = 570
    response.stages[0]!.updatedAt = '2026-10-28T06:00:05Z'
    await vi.advanceTimersByTimeAsync(5000); await flushPromises()
    expect(wrapper.text()).toContain('570')
    const chart = wrapper.findComponent({ name: 'ExperimentChart' })
    expect(chart.props('option').series[0].data).toEqual([560, 570])
    response.stages.push({ key: 'image_evaluation', title: '图片开发区评价', state: 'RUNNING_IMAGE_DEVELOPMENT_EVALUATION', availability: 'AVAILABLE', metrics: { processed: 3, total: 1064, baselineAccepted: 2, top20Accepted: 3, enhancedAccepted: 1, scopeCorrect: 1, failedQueries: 1 }, latest: {}, history: [] })
    await vi.advanceTimersByTimeAsync(5000); await flushPromises()
    expect(wrapper.text()).toContain('图片开发区评价')
    const imageChart = wrapper.findAllComponents({ name: 'ExperimentChart' }).find(c => c.props('title') === '正确来源检出数量')!
    expect(imageChart.props('option').series[0].data).toEqual([2, 3, 1, 1])
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.formalProgress).toHaveBeenCalledTimes(3)
  } finally { if (wrapper.exists()) wrapper.unmount() }
})
