import { request } from './http'
export const sceneNames:Record<string,string>={TEXT_REUSE:'正文审核',PAIR_PREDICTION:'句对预测'}
export const deliveryStates:Record<string,string>={QUEUED:'排队中',VERIFYING:'核验中',READY:'可发布',FAILED:'失败',INTERRUPTED:'已中断',PENDING_APPROVAL:'待管理员批准',RUNNING:'准备参考作品',INDEXING:'构建与切换索引',COMPLETED:'入库完成',WAITING_INDEX:'等待索引'}
export interface Release {id:string;name:string;scene:string;organizationId:string;department:string;status:string;error:string;manifest?:{metrics?:{macro_f1:number};threshold?:number;family?:string;reloadRows?:number;profileId?:string;libraryGenerationId?:string;textConfig?:{method:string;configId:string};calibration?:{threshold:number;rows:number};development?:{knownCases:number;realNewsCases:number;candidate:{known:{positiveDocuments:number;completeCorrectSourceDocuments:number;normalDocuments:number;scopedNormalAlerts:number};realNewsAlertedDocuments:number}}}}
export interface TextProfile {profileId:string;name:string;libraryGenerationId:string}
export const textProfiles=()=>request<{items:TextProfile[]}>('/api/workbench/releases/text-profiles')
export interface Releases {items:Release[];total:number;pointers:Array<{scopeKey:string;releaseId:string|null}>;history:Array<{scopeKey:string;previousId:string|null;releaseId:string|null;createdAt:string}>}
export const releases=(page=1,pageSize=20)=>request<Releases>(`/api/workbench/releases?page=${page}&pageSize=${pageSize}`)
export const releaseEvaluations=(id:string)=>request<Array<{runId:string;name:string}>>(`/api/workbench/releases/models/${id}/evaluations`)
export const createRelease=(value:unknown)=>request<{id:string}>('/api/workbench/releases',{method:'POST',body:JSON.stringify(value)})
export const release=(id:string)=>request<Release & {active:boolean}>(`/api/workbench/releases/${encodeURIComponent(id)}`)
export const activate=(id:string,expectedId:string)=>request(`/api/workbench/releases/${id}/activate`,{method:'POST',body:JSON.stringify({expectedId})})
export const reset=(organizationId:string,scene:string,expectedId:string)=>request('/api/workbench/releases/reset',{method:'POST',body:JSON.stringify({organizationId,scene,expectedId})})
export interface ReleasedResult {releaseId:string;predictionId:string;rows:Array<{score:number;predicted:number;scoreType:string}>}
export const releasedPredict=(organizationId:string,rows:unknown[])=>request<ReleasedResult>('/api/workbench/releases/predict',{method:'POST',body:JSON.stringify({organizationId,rows})})
export interface ImportBatch {id:string;datasetId:string;versionId:string;name:string;status:string;processed:number;inserted:number;duplicates:number;rejected:number;generationId:string|null;error:string|null}
export interface ImportRow {rowNo:number;sourceId:string;status:string;referenceId:string|null;message:string}
export const imports=(page=1,pageSize=20)=>request<{items:ImportBatch[];total:number;activeGenerationId:string}>(`/api/workbench/reference-imports?page=${page}&pageSize=${pageSize}`)
export const createImport=(datasetId:string,versionId:string)=>request('/api/workbench/reference-imports',{method:'POST',body:JSON.stringify({datasetId,versionId})})
export const importAction=(id:string,action:string)=>request(`/api/workbench/reference-imports/${id}/${action}`,{method:'POST'})
export const importRows=(id:string,page=1,pageSize=20)=>request<{items:ImportRow[];total:number}>(`/api/workbench/reference-imports/${id}/rows?page=${page}&pageSize=${pageSize}`)
export const importBatch=(id:string)=>request<ImportBatch>(`/api/workbench/reference-imports/${encodeURIComponent(id)}`)

export const releaseHistory=(page=1,pageSize=20)=>request<{items:Releases['history'];total:number}>(`/api/workbench/releases/history?page=${page}&pageSize=${pageSize}`)
