import type {ModelBundle} from './api/training'
import type {FlowContext} from './api/flows'

export function bundleOwnsRun(bundle:ModelBundle,runId:string):boolean{
 return bundle.state.preparationId===runId||bundle.state.steps.some(step=>step.runId===runId)
}

export function trainingSelection(input:{dataset:string;version:string;preparation?:string;step:number;parentBundle?:string;parentModel?:string}):Record<string,string>{
 return {dataset:input.dataset,version:input.version,tab:'new',step:String(input.step),...(input.preparation?{preparation:input.preparation}:{}),...(input.parentBundle?{parentBundle:input.parentBundle}:{}),...(input.parentModel?{parentModel:input.parentModel}:{})}
}

export function continuationAnchor(bundle:ModelBundle):string{
 const members=bundle.state.models
 if(bundle.status!=='COMPLETED'||bundle.evaluatedCount!==6||new Set(members.map(m=>m.family)).size!==6)throw new Error('请等待完整模型组训练与评价完成')
 const bert=members.find(m=>m.family==='bert')
 if(!bert)throw new Error('起始模型组缺少 BERT 成员')
 return bert.modelId
}

export function bindBundleContext(context:FlowContext,bundle:ModelBundle):FlowContext{
 const next={...context}
 const version=bundle.state.cleanVersionId||bundle.inputVersionId||(context.datasetId===bundle.datasetId?context.versionId:undefined)
 if(context.datasetId!==bundle.datasetId||context.versionId!==version)delete next.importId
 if(next.bundleId!==bundle.pipelineId){for(const key of ['preparationId','trainingRunId','modelId','evaluationRunId','releaseId'] as const)delete next[key]}
 next.bundleId=bundle.pipelineId;next.datasetId=bundle.datasetId
 if(version)next.versionId=version;else delete next.versionId
 if(bundle.state.preparationId)next.preparationId=bundle.state.preparationId
 else delete next.preparationId
 const canonical=bundle.state.models.find(member=>member.family==='bert')
 if(canonical){next.trainingRunId=canonical.modelId;next.modelId=canonical.modelId;if(canonical.evaluationRunId)next.evaluationRunId=canonical.evaluationRunId;else delete next.evaluationRunId}
 else{delete next.trainingRunId;delete next.modelId;delete next.evaluationRunId}
 return next
}
