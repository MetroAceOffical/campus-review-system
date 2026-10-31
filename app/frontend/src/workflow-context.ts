import { shallowReactive } from 'vue'
import type { Detail } from './api/workbench'
import { workflowDestination } from './workbench-guidance'
import { activeFlow } from './flow-session'
import { flowDestination, flowSteps } from './flow-navigation'

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
  if(activeFlow.value){
    const flow=activeFlow.value
    const stage=({'/datasets':'quality','/training':'train','/models':'evaluate','/reference-imports':'library'} as Record<string,string>)[path]
    if(stage){
      const target=stage==='train'&&!flowSteps(flow,workflowContext.dataset).find(s=>s.key==='train')?.enabled?'prepare':stage
      return flowDestination(flow,target)
    }
    if(['/references','/releases'].includes(path))return{path,query:{flow:flow.flowId,...(flow.context.datasetId?{dataset:flow.context.datasetId}:{}),...(flow.context.versionId?{version:flow.context.versionId}:{})}}
  }
  const { dataset, version } = workflowContext
  if (!dataset || !version) return path
  const stage = ({ '/datasets': 'clean', '/training': 'train', '/models': 'evaluate', '/reference-imports': 'library' } as Record<string, string>)[path]
  if (stage) { const to=currentDestination(stage);if(activeFlow.value)to.query.flow=activeFlow.value.flowId;return to }
  if (['/references', '/releases'].includes(path)) return { path, query: { dataset: dataset.datasetId, version,...(activeFlow.value?{flow:activeFlow.value.flowId}:{}) } }
  return path
}
