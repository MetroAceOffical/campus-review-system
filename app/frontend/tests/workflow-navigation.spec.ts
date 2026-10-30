import { describe, expect, it } from 'vitest'
import { workflowDestination, workflowStages } from '../src/workbench-guidance'
import { workflowContext, contextualLink } from '../src/workflow-context'
import type { Detail } from '../src/api/workbench'

const data = { datasetId:'data',name:'新闻中心',kind:'PAIRS',purpose:'TRAIN',versions:[{versionId:'raw',stage:'RAW',status:'READY'},{versionId:'clean',parentVersionId:'raw',stage:'CLEAN',status:'READY'}],runs:[{runId:'trained',inputVersionId:'clean',action:'TRAIN',status:'COMPLETED'}] } as unknown as Detail
describe('actual workflow destinations',()=>{
  it('opens the completed training task and its exact model evaluation',()=>{
    expect(workflowDestination(data,'clean','train')).toEqual({path:'/training',query:{dataset:'data',version:'clean',run:'trained'}})
    expect(workflowDestination(data,'clean','evaluate')).toEqual({path:'/models',query:{dataset:'data',version:'clean',model:'trained',tab:'evaluation'}})
  })
  it('returns to the original raw version for its quality assessment',()=>{
    expect(workflowDestination(data,'clean','audit')).toEqual({path:'/datasets',query:{dataset:'data',version:'raw'}})
    expect(workflowDestination(data,'clean','clean')).toEqual({path:'/datasets',query:{dataset:'data',version:'clean'}})
  })
  it('opens an existing import result rather than another creation form',()=>{
    const news={...data,kind:'NEWS',purpose:'LIBRARY',referenceImports:[{id:'batch',versionId:'clean',status:'COMPLETED'}]} as Detail
    expect(workflowDestination(news,'clean','library')).toEqual({path:'/reference-imports',query:{dataset:'data',version:'clean',batch:'batch',tab:'records'}})
  })
  it('retains the selected model and does not borrow another models evaluation',()=>{
    workflowContext.dataset=data; workflowContext.version='clean'; workflowContext.run='older'; workflowContext.model='older'
    expect(contextualLink('/models')).toEqual({path:'/models',query:{dataset:'data',version:'clean',model:'older',tab:'evaluation'}})
    const detail={...data,runs:[{runId:'eval-old',inputVersionId:'clean',action:'EVALUATE',status:'COMPLETED',options:{modelId:'older'}},...data.runs]} as Detail
    expect(workflowStages(detail,'clean').find(s=>s.key==='evaluate')?.status).toBe('waiting')
    workflowContext.dataset=undefined; workflowContext.model=undefined; workflowContext.run=undefined
  })
})
