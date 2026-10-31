import {mount,flushPromises} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import {defineComponent} from 'vue'
import ElementPlus from 'element-plus'
import {afterEach,expect,it,vi} from 'vitest'
import ModelView from '../src/views/ModelView.vue'
import TrainingView from '../src/views/TrainingView.vue'
import {activeFlow} from '../src/flow-session'
import {workflowContext} from '../src/workflow-context'

const {request,session}=vi.hoisted(()=>({request:vi.fn(),session:{user:{role:'ADMIN'},loaded:true}}))
vi.mock('../src/api/http',()=>({request}))
vi.mock('../src/session',()=>({session}))
const page=(items:unknown[]=[])=>({items,total:items.length})
const flow={flowId:'flow',kind:'CONTINUE' as const,name:'继续训练',revision:1,context:{},createdAt:'',updatedAt:''}
const data={datasetId:'news',organizationId:'1',kind:'PAIRS',name:'正式数据',versions:[{versionId:'clean',stage:'CLEAN',status:'READY'}],runs:[]}
const model={modelId:'cnn',runId:'cnn',bundleId:'parents',datasetId:'news',inputVersionId:'clean',organizationId:'1',family:'cnn',name:'CNN',archived:false,manifest:{family:'cnn',trainRows:5000,validationRows:600,elapsedSeconds:100,reloadMaxDifference:0,validation:{macro_f1:.7,accuracy:.7,precision:.7,recall:.7,f1:.7,roc_auc:.7},parameters:{width:64}}}
const run=(id:string)=>({runId:id,datasetId:'news',inputVersionId:'clean',status:'COMPLETED',action:'TRAIN',options:{family:'cnn'},result:{}})
const stubs={...Object.fromEntries(['ModelBundles','ModelComparison','TrainingProgress','EvaluationCharts','PredictionAnalysis','ExperimentAnalysis','PredictionResults','ParentModelComparison','FormalTrainingProgress','NewsSampleReport','ExperimentChart'].map(name=>[name,true])),AutomaticPipeline:defineComponent({name:'AutomaticPipeline',props:['focusId'],inheritAttrs:false,template:'<div />'})}
const settle=async()=>{for(let i=0;i<4;i++)await flushPromises()}
afterEach(()=>{request.mockReset();activeFlow.value=undefined;workflowContext.bundle=undefined;workflowContext.dataset=undefined;workflowContext.run=undefined;workflowContext.model=undefined})

it('refreshes historical member details without selecting a parent, then selects its complete group BERT',async()=>{
 const writes:Array<Record<string,unknown>>=[]
 activeFlow.value=flow
 request.mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path==='/api/workbench/flows/flow'){
   if(options?.method==='PATCH'){const edit=JSON.parse(String(options.body));writes.push(edit.context);return {...flow,context:edit.context,currentStep:edit.step,revision:2}}
   return flow
  }
  if(path==='/api/workbench/pipelines/parents')return {pipelineId:'parents',datasetId:'news',status:'COMPLETED',evaluatedCount:6,state:{models:['lr','svm','rf','cnn','bilstm','bert'].map(family=>({family,modelId:family==='cnn'?'cnn':`parent-${family}`}))}}
  if(path==='/api/workbench/training/models/cnn')return model
  if(path.includes('/models/cnn/versions'))return page([model])
  if(path==='/api/workbench/datasets/news')return data
  if(path==='/api/workbench/runs/cnn')return run('cnn')
  if(path.startsWith('/api/workbench/training/model-groups')||path.startsWith('/api/workbench/training/runs?')||path.startsWith('/api/workbench/datasets?'))return page()
  throw new Error('Unexpected request '+path)
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/models',component:ModelView},{path:'/datasets',component:{template:'<div />'}}]})
 await router.push('/models?flow=flow&selectParent=1&model=cnn&tab=versions');await router.isReady()
 const wrapper=mount(ModelView,{global:{plugins:[ElementPlus,router],stubs}})
 try{
  await settle();expect(writes).toHaveLength(0)
  const select=wrapper.findAll('button').find(b=>b.text()==='选择该版本');expect(select).toBeDefined()
  await select!.trigger('click');await settle()
  expect(writes).toEqual([{parentModelId:'parent-bert'}]);expect(router.currentRoute.value.path).toBe('/datasets')
 }finally{wrapper.unmount()}
})

it('leaves group A for a new task and opens unrelated history B without inheriting A',async()=>{
 request.mockImplementation(async(path:string)=>{
  if(path.startsWith('/api/workbench/datasets?'))return page([data])
  if(path==='/api/workbench/datasets/news')return data
  if(path.startsWith('/api/workbench/training/runs?'))return page([run('history-b')])
  if(path==='/api/workbench/runs/history-b')return run('history-b')
  if(path.startsWith('/api/workbench/runs/history-b/events'))return []
  throw new Error('Unexpected request '+path)
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/training',component:TrainingView},{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
 await router.push('/training?dataset=news&version=clean&bundle=group-a&tab=tasks');await router.isReady()
 const wrapper=mount(TrainingView,{global:{plugins:[ElementPlus,router],stubs}})
 try{
  await settle();expect(wrapper.findComponent({name:'AutomaticPipeline'}).props('focusId')).toBe('group-a')
  await wrapper.findAll('button').find(b=>b.text()==='新建训练')!.trigger('click');await settle()
  expect(wrapper.findComponent({name:'AutomaticPipeline'}).props('focusId')).toBe('')
  await wrapper.findAll('button').find(b=>b.text()==='查看')!.trigger('click');await settle()
  expect(router.currentRoute.value.query.run).toBe('history-b');expect(router.currentRoute.value.query.bundle).toBeUndefined()
 }finally{wrapper.unmount()}
})
