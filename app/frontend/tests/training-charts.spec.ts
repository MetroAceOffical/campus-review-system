import {expect,it} from 'vitest'
import {shallowMount} from '@vue/test-utils'
import EvaluationCharts from '../src/components/workbench/EvaluationCharts.vue'
import {trainingCharts} from '../src/training-charts'
import {comparableGroups,learningGroups,heatmapGroups,experimentCharts,modelCharts} from '../src/experiment-charts'
import {evaluationCharts} from '../src/evaluation-charts'
import {comparisonCharts} from '../src/comparison-charts'
it('keeps six numeric metric cards visible in the compact metrics-only view',()=>{
 const metrics={rows:2,accuracy:1,precision:1,recall:1,f1:1,macro_f1:1,roc_auc:1,average_precision:1,confusionMatrix:[[1,0],[0,1]],roc:[],pr:[]}
 const wrapper=shallowMount(EvaluationCharts,{props:{metrics,view:'metrics'}})
 for(const label of ['Accuracy','Precision','Recall','F1','Macro-F1','ROC AUC'])expect(wrapper.text()).toContain(label)
 wrapper.unmount()
})
it('keeps missing measurements missing and compares only matching experiment identities',()=>{
 const charts=trainingCharts([{sequence:1,data:{stage:'TRAINING',epoch:1,step:1,loss:2}},{sequence:2,data:{stage:'TRAINING',epoch:1,step:2,loss:1}}] as any)
 expect(charts.find(c=>c.key==='loss')?.ready).toBe(true)
 expect(charts.find(c=>c.key==='memory')?.ready).toBe(false)
 const row={modelId:'a',family:'bert',manifest:{inputSha256:'input',preparationSha256:'split',validationDataSha256:'holdout',initialization:{weightsSha256:'a'.repeat(64),encoderSha256:'b'.repeat(64)},parameters:{seed:1,epochs:3},trainRows:24}} as any
 expect(comparableGroups([row,{...row,modelId:'b',manifest:{...row.manifest,preparationSha256:'different'}}])).toHaveLength(2)
 expect(learningGroups([row,{...row,modelId:'b',manifest:{...row.manifest,trainRows:48}},{...row,modelId:'c',manifest:{...row.manifest,trainRows:96,parameters:{seed:2,epochs:3}}}])).toHaveLength(1)
 expect(learningGroups([row,{...row,modelId:'other',manifest:{...row.manifest,trainRows:48,initialization:{weightsSha256:'a'.repeat(64),encoderSha256:'c'.repeat(64)}}}])).toHaveLength(0)
})
it('does not offer test threshold tuning and conserves parent-child flow counts',()=>{
 const metrics={rows:12,confusionMatrix:[[5,1],[2,4]],roc:[],pr:[],accuracy:.75,precision:.8,recall:.7,f1:.75,macro_f1:.75,roc_auc:null} as any
 expect(evaluationCharts(metrics,{available:true,partition:'test',confusionMatrix:metrics.confusionMatrix,histogram:[],reliability:[],lengthErrors:[],scoreType:'margin'} as any).some(c=>c.key==='threshold'||c.key==='reliability')).toBe(false)
 expect(comparisonCharts({parentMetrics:metrics,childMetrics:metrics} as any,undefined).find(c=>c.key==='version-flow')?.ready).toBe(false)
 const flow=comparisonCharts({parentMetrics:metrics,childMetrics:{...metrics,confusionMatrix:[[6,0],[2,4]]}} as any,{improved:2,regressed:1}).find(c=>c.key==='version-flow')!
 expect(flow.option.series[0].links.reduce((s:number,l:any)=>s+l.value,0)).toBe(12)
})

it('separates initial encoders and aggregates repeated heatmap cells explicitly',()=>{
 const row={modelId:'a',name:'实验',family:'bert',manifest:{initialization:{weightsSha256:'a'.repeat(64),encoderSha256:'b'.repeat(64)},parameters:{learning_rate:.001,batch_size:32,seed:1},validation:{macro_f1:.5}}} as any
 const repeated={...row,modelId:'b',manifest:{...row.manifest,validation:{macro_f1:.9}}}
 const different={...row,modelId:'c',manifest:{...row.manifest,initialization:{weightsSha256:'c'.repeat(64),encoderSha256:'b'.repeat(64)}}}
 expect(heatmapGroups([row,repeated,different],'learning_rate','batch_size')).toHaveLength(2)
 const cells=experimentCharts([row,repeated,different],'learning_rate','batch_size').find(c=>c.key==='parameter-grid')!.option.series[0].data
 expect(cells).toHaveLength(1);expect(cells[0][2]).toBeCloseTo(.7);expect(cells[0][4]).toBe(2)
 const names=modelCharts([row,repeated]).find(c=>c.key==='model-radar')!.option.series[0].data.map((d:any)=>d.name);expect(new Set(names).size).toBe(2)
})
