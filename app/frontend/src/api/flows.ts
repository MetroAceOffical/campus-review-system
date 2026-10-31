import { request } from './http'
import type { Page } from './workbench'
export type FlowKind='UPLOAD'|'TRAIN'|'CONTINUE'|'LIBRARY'
export interface FlowContext { bundleId?:string; datasetId?:string;versionId?:string;preparationId?:string;trainingRunId?:string;evaluationRunId?:string;modelId?:string;parentModelId?:string;importId?:string;releaseId?:string }
export interface Flow {currentStep?:string;flowId:string;kind:FlowKind;name:string;revision:number;context:FlowContext;createdAt:string;updatedAt:string}
export const flowNames:Record<FlowKind,string>={UPLOAD:'上传数据集',TRAIN:'新建模型训练',CONTINUE:'继续训练已有模型',LIBRARY:'加入参考库'}
export const createFlow=(kind:FlowKind,requestId:string)=>request<Flow>('/api/workbench/flows',{method:'POST',body:JSON.stringify({kind,requestId})})
export const getFlow=(id:string)=>request<Flow>(`/api/workbench/flows/${encodeURIComponent(id)}`)
export const updateFlow=(flow:Flow,context:FlowContext,step=flow.currentStep)=>request<Flow>(`/api/workbench/flows/${encodeURIComponent(flow.flowId)}`,{method:'PATCH',body:JSON.stringify({revision:flow.revision,context,step})})
export const listFlows=(page=1,pageSize=12,q='')=>request<Page<Flow>>(`/api/workbench/flows?${new URLSearchParams({page:String(page),pageSize:String(pageSize),q})}`)
