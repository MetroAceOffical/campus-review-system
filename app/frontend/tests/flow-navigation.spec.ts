import { expect,it } from 'vitest'
import { flowSteps,flowDestination } from '../src/flow-navigation'
import type { Flow } from '../src/api/flows'
import type { Detail } from '../src/api/workbench'
import { activeFlow } from '../src/flow-session'
import { contextualLink,workflowContext } from '../src/workflow-context'
const detail={datasetId:'data',kind:'PAIRS',purpose:'TRAIN',versions:[{versionId:'clean',stage:'CLEAN',status:'READY'}],runs:[{runId:'other-model',inputVersionId:'clean',action:'TRAIN',status:'COMPLETED'}]} as unknown as Detail
it('keeps this task independent of other completed models and resumes its exact objects',()=>{
  const flow:Flow={flowId:'flow',kind:'TRAIN',name:'新模型训练',revision:1,context:{datasetId:'data',versionId:'clean'},createdAt:'',updatedAt:''}
  expect(flowSteps(flow,detail).find(s=>s.key==='train')?.status).toBe('waiting')
  expect(flowSteps(flow,detail).find(s=>s.key==='evaluate')?.enabled).toBe(false)
  const trained={...flow,context:{...flow.context,trainingRunId:'own',modelId:'own'}}
  expect(flowDestination(trained,'evaluate')).toEqual({path:'/models',query:{flow:'flow',dataset:'data',version:'clean',model:'own',tab:'evaluation'}})
  expect(flowDestination({...flow,kind:'CONTINUE'},'parent').path).toBe('/models')
  activeFlow.value=flow;workflowContext.dataset=detail;workflowContext.version='clean';workflowContext.run='other-model';workflowContext.model='other-model'
  expect(contextualLink('/training')).toEqual(flowDestination(flow,'prepare'))
  expect(contextualLink('/models')).toEqual(flowDestination(flow,'evaluate'))
  activeFlow.value=undefined
})
