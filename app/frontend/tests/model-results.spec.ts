import { expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import type { Component } from 'vue'
import ModelComparison from '../src/components/workbench/ModelComparison.vue'
import PredictionResults from '../src/components/workbench/PredictionResults.vue'
import type { Model, Metrics } from '../src/api/training'

const api = vi.hoisted(() => ({ predictions: vi.fn(), artifact: (id: string) => `/results/${id}`, modelNames: { lr: 'LR', svm: 'SVM' } }))
vi.mock('../src/api/training', () => api)
const stubs: Record<string, boolean | Component> = Object.fromEntries(['el-table', 'el-table-column', 'el-button', 'el-select', 'el-option', 'el-input', 'el-pagination', 'RouterLink'].map(name => [name, true]))
stubs['el-table'] = { name: 'ElTable', props: ['data'], template: '<div />' }

test('keeps comparison charts within one data split and paginates filtered complete results', async () => {
  const metrics: Metrics = { rows: 20, accuracy: .8, precision: .8, recall: .8, f1: .8, macro_f1: .8, roc_auc: .9, average_precision: .9, confusionMatrix: [[8, 2], [2, 8]], roc: [], pr: [] }
  const model = (id: string, preparation: string, score: number): Model => ({ modelId: id, name: id, family: 'lr', organizationId: '1', datasetId: 'dataset', datasetName: '训练句对', runId: id, archived: false, createdAt: '', manifest: { family: 'lr', trainRows: 80, validationRows: 20, inputSha256: 'input', preparationSha256: preparation, validation: { ...metrics, macro_f1: score }, parameters: { C: 1 }, elapsedSeconds: 2, bestEpoch: null, iterations: 5, converged: true, reloadMaxDifference: 0 } })
  const comparison = shallowMount(ModelComparison, { props: { models: [model('LR1', 'same', .7), model('LR2', 'same', .8), model('LR3', 'other', .9)] }, global: { stubs } })
  try {
    const bars = comparison.findAllComponents({ name: 'ExperimentChart' })[0]!
    expect(bars.props('option').xAxis.data).toEqual(['LR1', 'LR2'])
    expect(bars.props('option').series.find((row: { name: string }) => row.name === 'Macro-F1').data).toEqual([.7, .8])
    comparison.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'input:other:20')
    await flushPromises()
    expect(bars.props('option').xAxis.data).toEqual(['LR3'])
  } finally { comparison.unmount() }

  api.predictions.mockResolvedValue({ items: [{ id: '101', sentence1: '原文', sentence2: '改写', score: .6, predicted: 1, label: 0, outcome: 'FP' }], total: 70, count: 200, page: 1, pageSize: 20 })
  const results = shallowMount(PredictionResults, { props: { runId: 'run', action: 'EVALUATE', inputName: 'news.csv' }, global: { stubs, directives: { loading: () => {} } } })
  try {
    await flushPromises()
    expect(results.text()).toContain('70 / 200条')
    expect(results.text()).toContain('news.csv')
    const selects = results.findAllComponents({ name: 'ElSelect' })
    selects[1]!.vm.$emit('update:modelValue', 'FP'); selects[1]!.vm.$emit('change', 'FP'); await flushPromises()
    expect(api.predictions).toHaveBeenLastCalledWith('run', 1, 20, '', '', 'FP')
    const pagination = results.findComponent({ name: 'RecordPagination' })
    pagination.vm.$emit('update:currentPage', 2); pagination.vm.$emit('change'); await flushPromises()
    expect(api.predictions).toHaveBeenLastCalledWith('run', 2, 20, '', '', 'FP')
    expect(results.findComponent({ name: 'ElTable' }).props('data')[0].id).toBe('101')
  } finally { results.unmount() }
})
