import { mount,flushPromises } from '@vue/test-utils'
import { EditorContent } from '@tiptap/vue-3'
import ElementPlus from 'element-plus'
import { expect,it,vi } from 'vitest'
import CampusEditor from '../src/components/CampusEditor.vue'
const {api}=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../src/api/http',()=>({request:api}))
it('serializes replacement uploads and keeps their target nodes fixed',async()=>{
  let first!:(value:unknown)=>void,second!:(value:unknown)=>void;let uploads=0
  api.mockImplementation((path:string)=>path==='/api/settings/limits'?Promise.resolve({titleCodePoints:200,bodyCodePoints:10000,images:6,imageBytes:10485760,imagePixels:20000000,imageSide:8000,urlCharacters:2000}):new Promise(resolve=>{uploads++;if(uploads===1)first=resolve;else second=resolve}))
  const wrapper=mount(CampusEditor,{props:{modelValue:{title:'测试',schemaVersion:'1',sources:[],content:{type:'doc',content:[{type:'campusImage',attrs:{nodeId:'a',fileId:'1',caption:'A',origin:'ORIGINAL',sourceUrl:''}},{type:'campusImage',attrs:{nodeId:'b',fileId:'2',caption:'B',origin:'ORIGINAL',sourceUrl:''}}]}}},global:{plugins:[ElementPlus]}})
  try{
    await flushPromises();const editor=wrapper.getComponent(EditorContent).props('editor')!;const input=wrapper.get('input[type="file"]')
    const choose=async(nodeId:string,name:string)=>{window.dispatchEvent(new CustomEvent('campus-replace-image',{detail:{editor,nodeId}}));Object.defineProperty(input.element,'files',{configurable:true,value:[new File(['fixture'],name,{type:'image/png'})]});await input.trigger('change');await flushPromises()}
    await choose('a','a.png');await choose('b','b.png');expect(uploads).toBe(1)
    first({fileId:'101'});await flushPromises();expect(editor.getJSON().content!.filter(n=>n.type==='campusImage').map(n=>[n.attrs!.nodeId,n.attrs!.fileId])).toEqual([['a','101'],['b','2']])
    expect(wrapper.emitted('uploading')).toEqual([[true],[false]])
    await choose('b','b.png');expect(uploads).toBe(2);second({fileId:'102'});await flushPromises();expect(editor.getJSON().content!.filter(n=>n.type==='campusImage').map(n=>[n.attrs!.nodeId,n.attrs!.fileId])).toEqual([['a','101'],['b','102']])
  }finally{first?.({fileId:'101'});second?.({fileId:'102'});await flushPromises();wrapper.unmount();api.mockReset()}
})
it('an upload finishing after unmount cannot clear the next page upload state or change its document',async()=>{
  let finish!:(value:unknown)=>void;const uploading=vi.fn(),update=vi.fn()
  api.mockImplementation(()=>new Promise(resolve=>finish=resolve))
  const wrapper=mount(CampusEditor,{props:{onUploading:uploading,'onUpdate:modelValue':update,modelValue:{title:'测试',schemaVersion:'1',sources:[],content:{type:'doc',content:[{type:'paragraph',attrs:{nodeId:'body'}}]}}},global:{plugins:[ElementPlus]}})
  await flushPromises();const input=wrapper.get('input[type="file"]');Object.defineProperty(input.element,'files',{configurable:true,value:[new File(['fixture'],'late.png',{type:'image/png'})]});await input.trigger('change');await flushPromises();wrapper.unmount();finish({fileId:'103'});await flushPromises()
  expect(uploading.mock.calls).toEqual([[true]]);expect(update).not.toHaveBeenCalled();api.mockReset()
})
