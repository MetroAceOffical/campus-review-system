import type { Flow } from './api/flows'
import type { Detail } from './api/workbench'
export interface FlowStep {key:string;label:string;status:'done'|'active'|'waiting'|'error';enabled:boolean}
const taskStatus=(state?:string):FlowStep['status']=>state==='COMPLETED'?'done':['RUNNING','QUEUED','INDEXING','PENDING_APPROVAL','VERIFYING','READY'].includes(state||'')?'active':['FAILED','CANCELLED','INTERRUPTED','WAITING_INDEX'].includes(state||'')?'error':'waiting'
export function flowSteps(flow:Flow,detail?:Detail):FlowStep[]{
  const c=flow.context,v=detail?.versions.find(v=>v.versionId===c.versionId),clean=v?.stage==='CLEAN'&&v.status==='READY'
  const run=(id?:string)=>id?detail?.runs.find(r=>r.runId===id):undefined
  const prepared=run(c.preparationId),ready=prepared?.status==='COMPLETED' && !!(prepared.result as {trainReady?:boolean})?.trainReady
  const release=detail?.modelReleases?.find(r=>r.id===c.releaseId)
  const rows:FlowStep[]=[]
  if(flow.kind==='CONTINUE')rows.push({key:'parent',label:'起始模型',status:c.parentModelId?'done':'waiting',enabled:true})
  rows.push({key:'data',label:flow.kind==='UPLOAD'?'上传与映射':'选择数据',status:c.datasetId?'done':'waiting',enabled:flow.kind!=='CONTINUE'||!!c.parentModelId},
    {key:'quality',label:'评估与清洗',status:clean?'done':c.datasetId?'active':'waiting',enabled:!!c.datasetId})
  const library=flow.kind==='LIBRARY'||flow.kind==='UPLOAD'&&['LIBRARY','BOTH'].includes(detail?.purpose||'')
  const train=['TRAIN','CONTINUE'].includes(flow.kind)||flow.kind==='UPLOAD'&&['TRAIN','BOTH'].includes(detail?.purpose||'')
  if(library)rows.push({key:'library',label:'参考入库',status:taskStatus(detail?.referenceImports?.find(b=>b.id===c.importId)?.status),enabled:!!clean})
  if(train)rows.push({key:'prepare',label:'准备样本',status:prepared?.status==='COMPLETED'&&!ready?'active':taskStatus(prepared?.status),enabled:!!clean},
    {key:'train',label:'训练模型',status:taskStatus(run(c.trainingRunId)?.status),enabled:!!ready},
    {key:'evaluate',label:'效果评价',status:taskStatus(run(c.evaluationRunId)?.status),enabled:!!c.modelId},
    {key:'predict',label:'试用与发布',status:release?.active?'done':taskStatus(release?.status),enabled:!!c.modelId})
  return rows
}
export function flowDestination(flow:Flow,step?:string):{path:string;query:Record<string,string>}{
  const c=flow.context,query:Record<string,string>={flow:flow.flowId}
  if(c.datasetId)query.dataset=c.datasetId;if(c.versionId)query.version=c.versionId
  step ||= flow.currentStep || (c.evaluationRunId?'evaluate':c.modelId?'evaluate':c.trainingRunId?'train':c.preparationId?'prepare':c.importId?'library':'')
  step ||= flow.kind==='CONTINUE'&&!c.parentModelId?'parent':!c.datasetId?'data':'quality'
  if(step==='parent')return{path:'/models',query:{...query,selectParent:'1'}}
  if(step==='library')return{path:'/reference-imports',query:{...query,...(c.importId?{batch:c.importId,tab:'records'}:{tab:'new'})}}
  if(step==='predict'&&c.releaseId)return{path:'/releases',query:{...query,release:c.releaseId,tab:'current'}}
  if(['prepare','train'].includes(step))return{path:'/training',query:{...query,...(c.parentModelId?{parentModel:c.parentModelId}:{}),...((step==='prepare'?c.preparationId:c.trainingRunId)?{run:(step==='prepare'?c.preparationId:c.trainingRunId)!}:{tab:'new',step:step==='prepare'?'0':'2'})}}
  if(['evaluate','predict'].includes(step))return{path:'/models',query:{...query,...(c.modelId?{model:c.modelId}:{}),...(step==='evaluate'&&c.evaluationRunId?{evaluation:c.evaluationRunId}:{}),tab:step==='evaluate'?'evaluation':'prediction'}}
  return{path:'/datasets',query:{...query,...(!c.datasetId&&flow.kind==='UPLOAD'?{import:'1'}:{})}}
}
