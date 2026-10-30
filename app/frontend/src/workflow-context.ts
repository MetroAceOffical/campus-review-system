import { shallowReactive } from 'vue'
import type { Detail } from './api/workbench'
import { workflowDestination } from './workbench-guidance'

// Only the current session's selection is kept; the URL carries it across refreshes.
export const workflowContext = shallowReactive<{ dataset?: Detail; version: string; run?: string; model?: string }>({ version: '' })
export function currentDestination(step: string) {
  const { dataset, version, run, model } = workflowContext
  if (!dataset) return { path: '/datasets', query: {} }
  const destination = workflowDestination(dataset, version, step)
  if (step === 'train' && run) destination.query = { dataset: dataset.datasetId, version, run }
  if (step === 'evaluate' && model) destination.query = { dataset: dataset.datasetId, version, model, tab: 'evaluation' }
  if (step === 'publish' && model) destination.query = { dataset: dataset.datasetId, version, modelId: model, tab: 'new' }
  return destination
}
export function contextualLink(path: string) {
  const { dataset, version } = workflowContext
  if (!dataset || !version) return path
  const stage = ({ '/datasets': 'clean', '/training': 'train', '/models': 'evaluate', '/reference-imports': 'library' } as Record<string, string>)[path]
  if (stage) return currentDestination(stage)
  if (['/references', '/releases'].includes(path)) return { path, query: { dataset: dataset.datasetId, version } }
  return path
}
