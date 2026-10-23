import { mount,flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import ElementPlus,{ ElMessageBox } from 'element-plus'
import { afterEach,expect,it,vi } from 'vitest'
import AppLayout from '../src/layouts/AppLayout.vue'
import EditorView from '../src/views/EditorView.vue'
import { session } from '../src/session'
const {api}=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../src/api/http',()=>({request:api}))
const config={titleCodePoints:200,bodyCodePoints:10000,images:6,imageBytes:10485760,imagePixels:20000000,imageSide:8000,urlCharacters:2000}
const empty=()=>({type:'doc',content:[]})
async function setup(){
  session.user={userId:'1',displayName:'测试成员',role:'MEMBER',organizations:[{organizationId:'1',name:'组织'}]};session.loaded=true
  api.mockImplementation(async(path:string,options?:RequestInit)=>{
    if(path==='/api/settings/limits')return config
    if(path==='/api/manuscripts'&&options?.method==='POST')return {manuscriptId:'3'}
    if(path==='/api/auth/logout')return {loggedOut:true}
    const id=path.match(/manuscripts\/(\d+)\/draft/)?.[1]
    if(id){const sent=options?.body?JSON.parse(String(options.body)):null;return {manuscriptId:id,organizationId:'1',status:'DRAFT',revision:sent?'1':'0',title:sent?.title??(id==='3'?'':'原稿'+id),schemaVersion:'1',content:sent?.content??empty(),sources:[],savedAt:'2026-10-23T01:00:00Z'}}
    throw new Error('Unexpected path '+path)
  })
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:AppLayout,children:[{path:'manuscripts',component:{template:'<p>稿件列表</p>'}},{path:'manuscripts/new',name:'new-manuscript',component:EditorView},{path:'manuscripts/:id/edit',component:EditorView}]},{path:'/login',component:{template:'<p>登录页</p>'}}]})
  await router.push('/manuscripts/1/edit');await router.isReady()
  const wrapper=mount(defineComponent({template:'<RouterView />'}),{global:{plugins:[ElementPlus,router],stubs:{CampusEditor:defineComponent({template:'<div />'})}}});await flushPromises();return {wrapper,router}
}
afterEach(()=>{vi.restoreAllMocks();api.mockReset();session.user=null;session.expired=false})
it('new draft mounts a new identity, parameter changes honor unsaved confirmation, and save targets the selected draft',async()=>{
  const {wrapper,router}=await setup();const confirm=vi.spyOn(ElMessageBox,'confirm')
  try{
    await router.push('/manuscripts/new');await flushPromises();expect(router.currentRoute.value.path).toBe('/manuscripts/3/edit')
    expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value','')
    await wrapper.get('input[aria-label="稿件标题"]').setValue('新稿内容');await wrapper.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises()
    expect(api.mock.calls.filter(([,o])=>o?.method==='PUT').map(([path])=>path)).toEqual(['/api/manuscripts/3/draft'])
    await wrapper.get('input[aria-label="稿件标题"]').setValue('未保存内容');confirm.mockRejectedValueOnce('cancel');await router.push('/manuscripts/2/edit');await flushPromises()
    expect(router.currentRoute.value.path).toBe('/manuscripts/3/edit');expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value','未保存内容')
    confirm.mockResolvedValueOnce('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>);await router.push('/manuscripts/2/edit');await flushPromises();expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value','原稿2')
  }finally{wrapper.unmount()}
})
it('canceling the unsaved exit keeps the session usable before any logout request',async()=>{
  const {wrapper,router}=await setup();vi.spyOn(ElMessageBox,'confirm').mockResolvedValueOnce('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>).mockRejectedValueOnce('cancel')
  try{
    await wrapper.get('input[aria-label="稿件标题"]').setValue('保留的未保存内容');await wrapper.findAll('button').find(b=>b.text()==='退出')!.trigger('click');await flushPromises()
    expect(api.mock.calls.some(([path])=>path==='/api/auth/logout')).toBe(false);expect(session.user?.userId).toBe('1');expect(router.currentRoute.value.path).toBe('/manuscripts/1/edit')
    await wrapper.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises();expect(wrapper.text()).toContain('已保存')
  }finally{wrapper.unmount()}
})
