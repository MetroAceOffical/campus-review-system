import { shallowMount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import TrainingProgress from '../src/components/workbench/TrainingProgress.vue'
import type { ComputeRun } from '../src/api/training'

it('shows the completed training epoch rather than the next checkpoint epoch',()=>{
  const run:ComputeRun={runId:'run',datasetId:'data',inputVersionId:'clean',outputVersionId:'',error:'',action:'TRAIN',status:'COMPLETED',options:{parameters:{epochs:3}}}
  const wrapper=shallowMount(TrainingProgress,{props:{run,events:[{sequence:1,data:{stage:'EPOCH',epoch:3,processed:24,total:24}},{sequence:2,data:{stage:'CHECKPOINT_SAVED',epoch:4}},{sequence:3,data:{stage:'COMPLETED'}}]}})
  expect(wrapper.text()).toContain('轮数3 / 3')
  expect(wrapper.text()).toContain('24 / 24')
  wrapper.unmount()
})
