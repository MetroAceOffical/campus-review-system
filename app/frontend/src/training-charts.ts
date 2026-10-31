import type {ComputeEvent} from './api/training'
export interface ChartSpec {key:string;title:string;group:string;ready:boolean;option:any;empty?:string;note?:string}
export const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)
export const chartBase={grid:{left:58,right:24,top:45,bottom:48},tooltip:{trigger:'axis',borderRadius:0},aria:{enabled:true},dataZoom:[{type:'inside'},{type:'slider',height:10,bottom:4}]}
export function trainingCharts(events:ComputeEvent[],history:Array<Record<string,unknown>>=[]):ChartSpec[]{
 const batches=events.filter(e=>e.data.stage==='TRAINING'&&finite(e.data.loss)).map(e=>e.data as any)
 const epochMap=new Map<string,any>();for(const p of [...history,...events.filter(e=>e.data.stage==='EPOCH'||e.data.trees!==undefined&&e.data.validation).map(e=>e.data)])if(p.epoch!==undefined||p.trees!==undefined)epochMap.set(`${p.epoch!==undefined?'epoch':'trees'}:${p.epoch??p.trees}`,p)
 const epochs=[...epochMap.values()].sort((a,b)=>(a.epoch??a.trees)-(b.epoch??b.trees))
 const x=batches.map(p=>`${p.epoch??1}:${p.step??0}`),ex=epochs.map(p=>p.epoch??p.trees)
 const line=(rows:any[],labels:any[],fields:[string,(p:any)=>unknown][],unit='',extra:any={})=>({...chartBase,legend:{},xAxis:{type:'category',data:labels},yAxis:{type:'value',name:unit},series:fields.map(([name,get])=>({name,type:'line',showSymbol:false,connectNulls:false,data:rows.map(p=>finite(get(p))?get(p):null)})),...extra})
 const spec=(key:string,title:string,group:string,ready:boolean,option:any,empty='后续训练将记录此项'):ChartSpec=>({key,title,group,ready,option,empty})
 const avg=batches.map((_,i)=>{const s=batches.slice(Math.max(0,i-9),i+1);return s.reduce((n,p)=>n+p.loss,0)/s.length})
 const quantile=(a:number[],q:number)=>a[Math.min(a.length-1,Math.floor((a.length-1)*q))]!
 const boxes=[...new Set(batches.map(p=>p.epoch??1))].map(epoch=>{const a=batches.filter(p=>(p.epoch??1)===epoch).map(p=>p.loss as number).sort((a,b)=>a-b);return{epoch,data:[a[0],quantile(a,.25),quantile(a,.5),quantile(a,.75),a[a.length-1]]}})
 const metricFields=[['准确率','accuracy'],['精确率','precision'],['召回率','recall'],['F1','f1'],['Macro-F1','macro_f1']] as const
 return [
 spec('loss','批次损失与平滑趋势','训练动态',batches.length>0,{...line(batches,x,[['批次损失',p=>p.loss]],'Loss'),series:[{name:'批次损失',type:'line',showSymbol:false,lineStyle:{width:1,opacity:.45},data:batches.map(p=>p.loss)},{name:'最近10批次均值',type:'line',showSymbol:false,lineStyle:{width:3},data:avg}]}),
 spec('epoch-loss','训练与验证损失','训练动态',epochs.some(p=>finite(p.validationLoss)),line(epochs,ex,[['训练集评估损失',p=>p.trainMetrics?.loss],['验证集损失',p=>p.validationLoss]],'Loss')),
 spec('accuracy','训练与验证准确率','训练动态',epochs.some(p=>finite(p.trainMetrics?.accuracy)),line(epochs,ex,[['训练集准确率',p=>p.trainMetrics?.accuracy],['验证集准确率',p=>p.validation?.accuracy]],'比例',{yAxis:{type:'value',min:0,max:1}})),
 spec('metrics','验证指标变化','训练动态',epochs.some(p=>p.validation),line(epochs,ex,metricFields.map(([n,k])=>[n,p=>p.validation?.[k]]),'比例',{yAxis:{type:'value',min:0,max:1}})),
 spec('epoch-heatmap','轮次与验证指标','训练动态',epochs.some(p=>p.validation),{...chartBase,xAxis:{type:'category',data:ex},yAxis:{type:'category',data:metricFields.map(x=>x[0])},visualMap:{min:0,max:1,show:false},series:[{type:'heatmap',label:{show:true,formatter:(p:any)=>(p.value[2]*100).toFixed(1)+'%'},data:epochs.flatMap((p,x)=>metricFields.flatMap(([,k],y)=>finite(p.validation?.[k])?[[x,y,p.validation[k]]]:[]))}]}),
 spec('loss-box','已加载批次损失分布','训练动态',boxes.length>0,{...chartBase,xAxis:{type:'category',data:boxes.map(b=>b.epoch)},yAxis:{type:'value',name:'Loss'},series:[{type:'boxplot',name:'批次损失分布',data:boxes.map(b=>b.data)}]}),
 spec('gradient','更新前梯度范数','梯度与学习率',batches.some(p=>finite(p.gradientNorm)),line(batches,x,[['梯度范数',p=>p.gradientNorm]],'L2')),
 spec('learning-rate','学习率','梯度与学习率',batches.some(p=>finite(p.learningRate)),line(batches,x,[['学习率',p=>p.learningRate]],'学习率')),
 spec('duration','每轮训练耗时组成','资源效率',epochs.some(p=>finite(p.trainSeconds)),{...chartBase,legend:{},xAxis:{type:'category',data:ex},yAxis:{type:'value',name:'秒'},series:[['训练','trainSeconds'],['验证与训练集评估','validationSeconds'],['模型与检查点保存','checkpointSeconds']].map(([name,k])=>({name,type:'bar',stack:'duration',data:epochs.map(p=>finite(p[k!])?p[k!]:null)}))}),
 spec('throughput','批次处理速度','资源效率',batches.some(p=>finite(p.samplesPerSecond)&&p.batchSeconds>0),line(batches,x,[['样本/秒',p=>p.batchSeconds>0?p.samplesPerSecond:null]],'样本/秒')),
 spec('gpu','GPU显存分配','资源效率',batches.some(p=>finite(p.cudaAllocatedBytes)),line(batches,x,[['已分配',p=>finite(p.cudaAllocatedBytes)?p.cudaAllocatedBytes/1048576:null],['已保留',p=>finite(p.cudaReservedBytes)?p.cudaReservedBytes/1048576:null]],'MiB',{series:['cudaAllocatedBytes','cudaReservedBytes'].map((k,i)=>({name:i?'已保留':'已分配',type:'line',areaStyle:{opacity:.12},showSymbol:false,data:batches.map(p=>finite(p[k])?p[k]/1048576:null)}))}),'CUDA任务运行时记录显存'),
 spec('memory','进程内存与CPU使用','资源效率',batches.some(p=>finite(p.hostRssBytes)),{...line(batches,x,[['内存MiB',p=>finite(p.hostRssBytes)?p.hostRssBytes/1048576:null],['CPU使用率',p=>p.cpuPercent]]),yAxis:[{type:'value',name:'MiB'},{type:'value',name:'CPU %',min:0,max:100}],series:[{name:'进程内存',type:'line',areaStyle:{opacity:.12},showSymbol:false,data:batches.map(p=>finite(p.hostRssBytes)?p.hostRssBytes/1048576:null)},{name:'CPU使用率',type:'line',yAxisIndex:1,showSymbol:false,data:batches.map(p=>finite(p.cpuPercent)?p.cpuPercent:null)}]})]
}
