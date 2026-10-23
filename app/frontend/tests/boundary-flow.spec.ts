import { expect,it,vi } from 'vitest'
import { mount,flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createRouter,createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import EditorView from '../src/views/EditorView.vue'
const {api}=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../src/api/http',()=>({request:api}))
import { documentSize,validationMessage } from '../src/editor/limits'
import type { DocumentInput } from '../src/types/document'
const limits={titleCodePoints:200,bodyCodePoints:10000,images:6,imageBytes:10485760,imagePixels:20000000,imageSide:8000,urlCharacters:2000}
it('counts Unicode code points and extracted paragraph breaks without truncating input',()=>{
  const value:DocumentInput={title:'😀'.repeat(200),schemaVersion:'1',content:{type:'doc',content:[{type:'paragraph',content:[{type:'text',text:'😀'.repeat(9998)},{type:'hardBreak'}]},{type:'paragraph',content:[]}]},sources:[]}
  expect(documentSize(value)).toEqual({title:200,body:10000,images:0});expect(validationMessage(value,limits)).toBe('')
  value.title+='😀';expect(validationMessage(value,limits)).toContain('标题');expect(value.title).toBe('😀'.repeat(201))
  value.title='测试';value.content.content![0]!.content!.push({type:'text',text:'中'});expect(validationMessage(value,limits)).toContain('正文')
})
it('uses the supplied server limit for images and URL length',()=>{
  const value:DocumentInput={title:'稿件',schemaVersion:'1',content:{type:'doc',content:Array.from({length:7},(_,i)=>({type:'campusImage',attrs:{nodeId:'i'+i,fileId:'1',caption:'不计入正文'}}))},sources:[]}
  expect(validationMessage(value,limits)).toContain('配图');expect(documentSize(value).body).toBe(0)
  value.content.content!.pop();expect(validationMessage(value,limits)).toBe('')
  expect(validationMessage(value,{...limits,images:5})).toContain('配图')
  value.sources=[{sourceId:'source',url:'https://example.org/'+ 'a'.repeat(2000)}];expect(validationMessage(value,limits)).toContain('链接')
})
it('keeps a 201-code-point title visible and blocks its save instead of truncating it',async()=>{
  api.mockImplementation(async(path:string)=>path==='/api/settings/limits'?limits:{manuscriptId:'boundary',organizationId:'1',status:'DRAFT',revision:'0',title:'原稿',schemaVersion:'1',content:{type:'doc',content:[]},sources:[],savedAt:'2026-10-23T01:00:00Z'})
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/manuscripts/:id/edit',component:EditorView}]});await router.push('/manuscripts/boundary/edit');await router.isReady()
  const wrapper=mount(EditorView,{global:{plugins:[ElementPlus,router],stubs:{CampusEditor:defineComponent({template:'<div />'})}}})
  try{await flushPromises();const title='😀'.repeat(201);await wrapper.get('input[aria-label="稿件标题"]').setValue(title);await flushPromises()
    expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value',title)
    expect(wrapper.text()).toContain('当前201个');await wrapper.findAll('button').find(b=>b.text()==='保存草稿')!.trigger('click');await flushPromises()
    expect(api.mock.calls.some(([,options])=>options?.method==='PUT')).toBe(false);expect(wrapper.get('input[aria-label="稿件标题"]').element).toHaveProperty('value',title)
  }finally{wrapper.unmount();api.mockReset()}
})
