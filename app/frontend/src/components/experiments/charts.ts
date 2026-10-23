import type { EChartsCoreOption } from 'echarts/core'
import type { ExperimentBundle,MetricValues } from '../../api/experiments'
export interface ChartSpec {title:string;note?:string;option:EChartsCoreOption}
export type MetricKey='accuracy'|'macro_f1'|'positive_precision'|'positive_recall'|'positive_f1'|'macro_precision'|'macro_recall'|'roc_auc'
export const metricNames:Record<MetricKey,string>={accuracy:'Accuracy',macro_f1:'Macro-F1',positive_precision:'正类 Precision',positive_recall:'正类 Recall',positive_f1:'正类 F1',macro_precision:'Macro-Precision',macro_recall:'Macro-Recall',roc_auc:'ROC AUC'}
function bars(title:string,names:string[],series:{name:string;data:(number|null)[]}[],note?:string,max?:number):ChartSpec{return {title,note,option:{grid:{top:50,bottom:65,left:65,right:25},legend:{},xAxis:{type:'category',data:names,axisLabel:{interval:names.length>8?'auto':0,rotate:names.length>8?40:0}},yAxis:{type:'value',max},series:series.map(row=>({...row,type:'bar'}))}}}
const labels=(b:ExperimentBundle)=>b.manifest.models.map(m=>m.label)
const values=(b:ExperimentBundle,set:string,fn:(v:MetricValues)=>number)=>b.manifest.models.map(m=>fn(b.metrics.sets[set].models[m.id]))
export function overview(b:ExperimentBundle,set:string,metric:MetricKey):ChartSpec[]{
  const selected=b.manifest.models.map(m=>b.search.configurations.find(r=>r.family===m.id&&r.selected)!)
  return [bars('六模型 · '+metricNames[metric],labels(b),[{name:metricNames[metric],data:values(b,set,v=>v[metric])}],undefined,1),
    bars('正类 Precision / Recall',labels(b),[{name:'正类 Precision',data:values(b,set,v=>v.positive_precision)},{name:'正类 Recall',data:values(b,set,v=>v.positive_recall)}],undefined,1),
    bars('端到端句对计时（ms/对）',labels(b),[{name:'ms/对',data:values(b,set,v=>v.end_to_end_ms_per_pair)}],'冻结实验batch8，CPU4线程；不含加载，不代表网站吞吐；传统CPU、神经GPU。'),
    bars('各划分的真实类别数量',Object.keys(b.metrics.splitCounts),[{name:'非复述 0',data:Object.values(b.metrics.splitCounts).map(s=>s.labels['0'])},{name:'复述 1',data:Object.values(b.metrics.splitCounts).map(s=>s.labels['1'])}],'测试子集包含在官方测试中，不能相加作为独立样本。'),
    bars('所选配置记录的资源峰值（MiB）',labels(b),[{name:'累计进程工作集峰值',data:selected.map(r=>r.peak_working_set_bytes===null?null:r.peak_working_set_bytes/1048576)},{name:'GPU allocated峰值',data:selected.map(r=>r.peak_allocated_bytes===null?null:r.peak_allocated_bytes/1048576)}],'工作集是进程累计值；GPU allocated不等于总显存；未记录值留空。')]
}
export function evaluation(b:ExperimentBundle,set:string,model:string):ChartSpec[]{
  const m=b.metrics.sets[set].models[model],c=b.curves.sets[set].models[model],cm=m.confusion_matrix,edges=c.histogram.edges
  return [{title:'混淆矩阵 · 真实行 / 预测列',option:{grid:{top:35,bottom:65,left:70,right:90},tooltip:{trigger:'item'},xAxis:{type:'category',data:['预测非复述 0','预测复述 1'],splitArea:{show:true}},yAxis:{type:'category',data:['真实非复述 0','真实复述 1'],inverse:true,splitArea:{show:true}},visualMap:{min:0,max:Math.max(...cm.flat()),orient:'vertical',right:0,top:'middle',calculable:true},series:[{type:'heatmap',data:cm.flatMap((row,y)=>row.map((v,x)=>[x,y,v])),label:{show:true}}]}},
    {title:'ROC 曲线',note:'由冻结逐条预测分数复算；AUC '+m.roc_auc.toFixed(6),option:{grid:{top:30,bottom:50,left:60,right:25},xAxis:{type:'value',name:'FPR',min:0,max:1},yAxis:{type:'value',name:'TPR',min:0,max:1},series:[{type:'line',showSymbol:false,data:c.roc.fpr.map((x,i)=>[x,c.roc.tpr[i]])}]}},
    {title:'Precision–Recall 曲线',note:'Average precision '+c.pr.averagePrecision.toFixed(6),option:{grid:{top:30,bottom:50,left:60,right:25},xAxis:{type:'value',name:'Recall',min:0,max:1},yAxis:{type:'value',name:'Precision',min:0,max:1},series:[{type:'line',showSymbol:false,data:c.pr.recall.map((x,i)=>[x,c.pr.precision[i]])}]}},
    bars(model==='svm'?'决策间隔分布（非概率）':'正类输出分数分布',edges.slice(0,-1).map((v,i)=>v.toFixed(2)+'~'+edges[i+1].toFixed(2)),[{name:'真实非复述',data:c.histogram.negative},{name:'真实复述',data:c.histogram.positive}],'20个区间，统计全部当前口径样本；输出分数不代表抄袭概率。'),
    bars('错误类型计数',['假阳性 FP','假阴性 FN'],[{name:'句对数',data:[m.errors.false_positive,m.errors.false_negative]}],'错误按冻结标签统计，未进行主观标签修正。')]
}
export function training(b:ExperimentBundle,model:string):ChartSpec[]{
  const runs=b.history.runs.filter(r=>r.family===model)
  const line=(title:string,value:(e:typeof runs[number]['epochs'][number])=>number,max?:number):ChartSpec=>({title,note:'仅验证集及实际训练轮；★为最终选定配置，未选定配置完整保留。',option:{legend:{},grid:{top:55,bottom:50,left:65,right:25},xAxis:{type:'value',name:'Epoch',min:1,minInterval:1,max:Math.max(...runs.flatMap(r=>r.epochs.map(e=>e.epoch)))},yAxis:{type:'value',max},series:runs.map(r=>({type:'line',name:(r.selected?'★ ':'')+'配置 '+r.index,data:r.epochs.map(e=>[e.epoch,value(e)]),symbolSize:8}))}})
  if(!runs.length)return []
  return [line('逐轮训练 Loss',e=>e.mean_train_loss),line('逐轮验证 Macro-F1',e=>e.validation_metrics.macro_f1,1),line('逐轮验证 Accuracy',e=>e.validation_metrics.accuracy,1),line('验证预测正类比例',e=>{const c=e.validation_metrics.confusion_matrix_0_1;return (c[0][1]+c[1][1])/c.flat().reduce((a,v)=>a+v,0)},1),line('逐轮验证前向耗时（秒）',e=>e.validation_forward_seconds)]
}
export function comparison(b:ExperimentBundle,model:string):ChartSpec[]{
  const rows=b.search.configurations.filter(r=>r.family===model),selected=b.manifest.models.map(m=>b.search.configurations.find(r=>r.family===m.id&&r.selected)!)
  return [bars('配置搜索 · 验证 Macro-F1',rows.map(r=>(r.selected?'★ ':'')+'配置 '+r.index),[{name:'验证 Macro-F1',data:rows.map(r=>r.validation_macro_f1)}],'模型仅依据验证集选定。',1),
    bars('六模型所选配置拟合 / 训练秒数',labels(b),[{name:'秒',data:selected.map(r=>r.fit_or_train_seconds)}],'不同设备及模型流程，不能直接推导网站吞吐。'),
    {title:'全部20配置 · 耗时与验证 Macro-F1',option:{legend:{},grid:{top:50,bottom:50,left:65,right:25},tooltip:{trigger:'item'},xAxis:{type:'value',name:'秒'},yAxis:{type:'value',name:'验证 Macro-F1',max:1},series:b.manifest.models.map(m=>({type:'scatter',name:m.label,data:b.search.configurations.filter(r=>r.family===m.id).map(r=>({name:'配置 '+r.index+(r.selected?' ★':''),value:[r.fit_or_train_seconds,r.validation_macro_f1]}))}))}},
    bars('各测试口径 · Macro-F1',labels(b),b.manifest.testSets.map(s=>({name:s.label,data:values(b,s.id,v=>v.macro_f1)})),'嵌套测试集合，差值不是独立重复试验或泛化能力的因果估计。',1),
    bars('预处理比较 · 验证 Macro-F1',b.search.preprocessingComparisons.map(p=>p.policy),[{name:'验证 Macro-F1',data:b.search.preprocessingComparisons.map(p=>p.validation_metrics.macro_f1)}],'已有冻结基线的预处理消融；不是六模型都分别进行的重训比较。',1)]
}
