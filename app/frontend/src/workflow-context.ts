import { shallowReactive } from 'vue'
import type {ModelBundle} from './api/training'
import type { Detail } from './api/workbench'
import { workflowDestination } from './workbench-guidance'
import { activeFlow } from './flow-session'
import { flowDestination, flowSteps } from './flow-navigation'

// Only the current session's selection is kept; the URL carries it across refreshes.
export const workflowContext = shallowReactive<{ dataset?: Detail; version: string; run?: string; model?: string;bundle?:ModelBundle }>({ version: '' })
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
      const steps=flowSteps(flow,workflowContext.dataset,workflowContext.bundle)
      if(path==='/models'&&!flow.context.modelId&&!flow.context.bundleId)return flow.kind==='CONTINUE'?flowDestination(flow,'parent'):{path,query:{flow:''}}
      if(!steps.some(s=>s.key===stage))return{path,query:{flow:''}}
      const target=stage==='train'&&!steps.find(s=>s.key==='train')?.enabled?'prepare':stage
      return flowDestination(flow,target)
    }
    if(path==='/releases'&&flow.context.bundleId)return flowDestination(flow,'predict')
    if(path==='/releases'&&flow.context.modelId)return{path,query:{flow:flow.flowId,modelId:flow.context.modelId,...(flow.context.releaseId?{release:flow.context.releaseId}:{}),...(flow.context.evaluationRunId?{evaluation:flow.context.evaluationRunId}:{})}}
    return{path,query:{flow:''}}
  }
  const { dataset, version } = workflowContext
  if (!dataset || !version) return path
  const stage = ({ '/datasets': 'clean', '/training': 'train', '/models': 'evaluate', '/reference-imports': 'library' } as Record<string, string>)[path]
  if (stage) return currentDestination(stage)
  if (['/references', '/releases'].includes(path)) return { path, query: { dataset: dataset.datasetId, version } }
  return path
}
