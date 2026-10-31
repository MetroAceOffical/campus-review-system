import type {ModelBundle} from './api/training'

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
