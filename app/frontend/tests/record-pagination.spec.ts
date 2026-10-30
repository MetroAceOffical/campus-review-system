import {mount} from '@vue/test-utils'
import ElementPlus from 'element-plus'
import {expect,test} from 'vitest'
import RecordPagination from '../src/components/RecordPagination.vue'
test('accepts a custom row count, resets the page, and keeps the direct page jumper',async()=>{
  const wrapper=mount(RecordPagination,{props:{currentPage:3,pageSize:20,total:240},global:{plugins:[ElementPlus]}})
  await wrapper.get('input[aria-label="自定义每页条数（1至100）"]').setValue('37')
  expect(wrapper.emitted('update:pageSize')).toEqual([[37]])
  expect(wrapper.emitted('update:currentPage')).toEqual([[1]])
  await wrapper.setProps({currentPage:1,pageSize:37})
  await wrapper.get('input[aria-label="跳转页码"]').setValue('5')
  await wrapper.findAll('button').find(button=>button.text()==='跳转')!.trigger('click')
  expect(wrapper.emitted('update:currentPage')?.at(-1)).toEqual([5])
  wrapper.unmount()
})
