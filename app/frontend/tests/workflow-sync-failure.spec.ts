import {mount,flushPromises} from '@vue/test-utils'
import {createMemoryHistory,createRouter} from 'vue-router'
import ElementPlus from 'element-plus'
import {expect,it,vi} from 'vitest'
import WorkflowNavigator from '../src/components/workbench/WorkflowNavigator.vue'
import {activeFlow} from '../src/flow-session'
import {workflowContext} from '../src/workflow-context'
const {request}=vi.hoisted(()=>({request:vi.fn()}))
vi.mock('../src/api/http',()=>({request}))
vi.mock('../src/session',()=>({session:{user:{userId:'admin',role:'ADMIN'}}}))

it('keeps a rejected flow update visible without retrying on its own transient dataset state',async()=>{
 let patches=0
 request.mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path==='/api/workbench/flows/flow'){
   if(options?.method==='PATCH'){
    patches++;if(patches>3)return new Promise(()=>{})
    throw new Error('模型与数据须属于同一部门')
   }
   return {flowId:'flow',kind:'CONTINUE',name:'继续训练',revision:1,context:{parentModelId:'parent'}}
  }
  if(path==='/api/workbench/datasets/news')return {datasetId:'news',versions:[{versionId:'clean',stage:'CLEAN'}],runs:[]}
  throw new Error('Unexpected request '+path)
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/datasets',component:{template:'<div />'}}]})
 await router.push('/datasets?flow=flow&dataset=news&version=clean');await router.isReady()
 const wrapper=mount(WorkflowNavigator,{global:{plugins:[ElementPlus,router]}})
 try{
  for(let i=0;i<6;i++)await flushPromises()
  expect(patches).toBeLessThanOrEqual(2)
  expect(wrapper.get('[role="alert"]').text()).toContain('模型与数据须属于同一部门')
  expect(wrapper.text()).toContain('重新读取')
  expect(wrapper.get('a[href*="selectParent=1"]').text()).toContain('起始模型')
 }finally{wrapper.unmount();request.mockReset();activeFlow.value=undefined;workflowContext.dataset=undefined;workflowContext.version='';workflowContext.model=undefined;workflowContext.run=undefined}
})

it('keeps the preparation flow visible for an existing split reused by a continued bundle',async()=>{
 let bundleReads=0
 const preparation={runId:'prepared',datasetId:'news',inputVersionId:'clean',action:'PREPARE',status:'COMPLETED',options:{},result:{trainReady:true}}
 const flow={flowId:'flow',kind:'CONTINUE',name:'继续训练',revision:1,currentStep:'train',context:{datasetId:'news',versionId:'clean',parentModelId:'parent',bundleId:'bundle',preparationId:'prepared'}}
 request.mockImplementation(async(path:string,options?:RequestInit)=>{
  if(path==='/api/workbench/flows/flow')return options?.method==='PATCH'?{...flow,context:JSON.parse(String(options.body)).context,currentStep:'prepare'}:flow
  if(path==='/api/workbench/pipelines/bundle'){if(++bundleReads>3)return new Promise(()=>{});return {pipelineId:'bundle',datasetId:'news',status:'RUNNING',trainedCount:0,evaluatedCount:0,state:{cleanVersionId:'clean',preparationId:'prepared',steps:[{stage:'TRAIN',runId:'child'}],models:[]}}}
  if(path==='/api/workbench/runs/prepared')return preparation
  if(path==='/api/workbench/datasets/news')return {datasetId:'news',name:'正式数据',kind:'PAIRS',versions:[{versionId:'clean',stage:'CLEAN',status:'READY'}],runs:[preparation]}
  throw new Error('Unexpected request '+path)
 })
 const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]})
 await router.push('/training?flow=flow&run=prepared&flowStep=prepare');await router.isReady()
 const wrapper=mount(WorkflowNavigator,{global:{plugins:[ElementPlus,router]}})
 try{
  for(let i=0;i<6;i++)await flushPromises()
  expect(bundleReads).toBeLessThanOrEqual(2)
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.get('a[aria-current="step"]').text()).toContain('准备样本')
  expect(wrapper.text()).toContain('正式数据')
 }finally{wrapper.unmount();request.mockReset();activeFlow.value=undefined;workflowContext.bundle=undefined;workflowContext.dataset=undefined;workflowContext.version='';workflowContext.model=undefined;workflowContext.run=undefined}
})
