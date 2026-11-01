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
 }finally{wrapper.unmount();request.mockReset();activeFlow.value=undefined;workflowContext.dataset=undefined;workflowContext.version='';workflowContext.model=undefined;workflowContext.run=undefined}
})
