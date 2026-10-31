import {expect,it} from 'vitest'
import {trainingSelection,continuationAnchor,bindBundleContext} from '../src/bundle-navigation'
import type {ModelBundle} from '../src/api/training'
it('keeps the parent group through data selection and parameter steps',()=>{
 const query=trainingSelection({dataset:'new-data',version:'clean',preparation:'samples',step:2,parentBundle:'old-group',parentModel:'old-bert'})
 expect(query.parentBundle).toBe('old-group');expect(query.parentModel).toBe('old-bert');expect(query.preparation).toBe('samples');expect(query.step).toBe('2')
})
it('uses the corresponding BERT parent as the common continuation identity',()=>{
 const bundle={status:'COMPLETED',evaluatedCount:6,state:{models:['lr','svm','rf','cnn','bilstm','bert'].map(family=>({family,modelId:`old-${family}`}))}} as ModelBundle
 expect(continuationAnchor(bundle)).toBe('old-bert')
 expect(()=>continuationAnchor({...bundle,status:'RUNNING'})).toThrow()
})
it('switches to a pending group without carrying another group model, split or release',()=>{
 const context=bindBundleContext({datasetId:'data',versionId:'clean',bundleId:'old',preparationId:'old-samples',modelId:'old-model',trainingRunId:'old-model',evaluationRunId:'old-eval',releaseId:'old-release',parentModelId:'parent-bert'},{pipelineId:'new',datasetId:'data',state:{cleanVersionId:'clean',stage:'PREPARE',models:[]}} as unknown as ModelBundle)
 expect(context.bundleId).toBe('new');expect(context.parentModelId).toBe('parent-bert')
 expect(context.preparationId).toBeUndefined();expect(context.modelId).toBeUndefined();expect(context.releaseId).toBeUndefined()
})
it('keeps a reference import only for the same dataset and clean version',()=>{
 const previous={datasetId:'news',versionId:'clean-a',importId:'old-import'}
 for(const [datasetId,cleanVersionId] of [['other-news','clean-a'],['news','clean-b']]){
  expect(bindBundleContext(previous,{pipelineId:'new',datasetId,state:{cleanVersionId,models:[]}} as unknown as ModelBundle).importId).toBeUndefined()
 }
 expect(bindBundleContext(previous,{pipelineId:'new',datasetId:'news',state:{cleanVersionId:'clean-a',models:[]}} as unknown as ModelBundle).importId).toBe('old-import')
 const raw=bindBundleContext(previous,{pipelineId:'raw-group',datasetId:'new-news',inputVersionId:'raw-b',state:{stage:'CLEAN',models:[]}} as unknown as ModelBundle)
 expect(raw.versionId).toBe('raw-b');expect(raw.importId).toBeUndefined()
})
