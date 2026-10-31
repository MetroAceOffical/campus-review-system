import { expect,it } from 'vitest'
import { flowSteps,flowDestination } from '../src/flow-navigation'
import type { Flow } from '../src/api/flows'
import type { Detail } from '../src/api/workbench'
import { activeFlow } from '../src/flow-session'
import { contextualLink,workflowContext } from '../src/workflow-context'
import type {ModelBundle} from '../src/api/training'
const detail={datasetId:'data',kind:'PAIRS',purpose:'TRAIN',versions:[{versionId:'clean',stage:'CLEAN',status:'READY'}],runs:[{runId:'other-model',inputVersionId:'clean',action:'TRAIN',status:'COMPLETED'}]} as unknown as Detail
it('keeps group training, evaluation and release on the same group across pages',()=>{
 const flow={flowId:'flow',kind:'TRAIN',context:{datasetId:'data',versionId:'clean',bundleId:'six'},currentStep:'train'} as Flow
 const group={pipelineId:'six',status:'RUNNING',trainedCount:4,evaluatedCount:3} as ModelBundle
 expect(flowSteps(flow,detail,group).find(s=>s.key==='train')?.status).toBe('active')
 expect(flowSteps(flow,detail,group).find(s=>s.key==='predict')?.enabled).toBe(false)
 expect(flowDestination(flow,'train').query.bundle).toBe('six')
 expect(flowDestination(flow,'evaluate').query.bundleId).toBe('six')
 expect(flowDestination(flow,'predict').query.bundleId).toBe('six')
 expect(flowSteps(flow,detail,{...group,status:'COMPLETED',trainedCount:6,evaluatedCount:6}).find(s=>s.key==='predict')?.enabled).toBe(true)
})
it('does not label training and evaluation as running while only cleaning is active',()=>{
 const flow={flowId:'flow',kind:'TRAIN',context:{datasetId:'data',versionId:'clean',bundleId:'six'}} as Flow
 const bundle={status:'RUNNING',trainedCount:0,evaluatedCount:0,state:{stage:'PREPARE',steps:[],models:[]}} as unknown as ModelBundle
 const steps=flowSteps(flow,detail,bundle)
 expect(steps.find(s=>s.key==='prepare')?.status).toBe('active')
 expect(steps.find(s=>s.key==='train')?.status).toBe('waiting')
 expect(steps.find(s=>s.key==='evaluate')?.status).toBe('waiting')
})
it('keeps this task independent of other completed models and resumes its exact objects',()=>{
  const flow:Flow={flowId:'flow',kind:'TRAIN',name:'新模型训练',revision:1,context:{datasetId:'data',versionId:'clean'},createdAt:'',updatedAt:''}
  expect(flowSteps(flow,detail).find(s=>s.key==='train')?.status).toBe('waiting')
  expect(flowSteps(flow,detail).find(s=>s.key==='evaluate')?.enabled).toBe(false)
  const trained={...flow,context:{...flow.context,trainingRunId:'own',modelId:'own'}}
  expect(flowDestination(trained,'evaluate')).toEqual({path:'/models',query:{flow:'flow',dataset:'data',version:'clean',model:'own',tab:'evaluation'}})
  expect(flowDestination({...flow,kind:'CONTINUE'},'parent').path).toBe('/models')
  const published={...trained,context:{...trained.context,releaseId:'own-release'}}
  const withOther={...detail,modelReleases:[{id:'other-release',versionId:'clean',status:'READY',active:true}]}
  expect(flowSteps(published,withOther).find(s=>s.key==='predict')?.status).toBe('waiting')
  expect(flowSteps(published,{...withOther,modelReleases:[{id:'own-release',versionId:'clean',status:'READY',active:true}]}).find(s=>s.key==='predict')?.status).toBe('done')
  expect(flowDestination(published,'predict')).toEqual({path:'/releases',query:{flow:'flow',dataset:'data',version:'clean',release:'own-release',tab:'current'}})
  activeFlow.value=flow;workflowContext.dataset=detail;workflowContext.version='clean';workflowContext.run='other-model';workflowContext.model='other-model'
  expect(contextualLink('/training')).toEqual(flowDestination(flow,'prepare'))
  expect(contextualLink('/models')).toEqual({path:'/models',query:{flow:''}})
  activeFlow.value={...flow,kind:'CONTINUE'}
  expect(contextualLink('/models')).toEqual(flowDestination(activeFlow.value,'parent'))
  activeFlow.value={...flow,kind:'LIBRARY'}
  expect(contextualLink('/training')).toEqual({path:'/training',query:{flow:''}})
  activeFlow.value=undefined
})
