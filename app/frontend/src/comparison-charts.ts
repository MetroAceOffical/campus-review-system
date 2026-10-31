import type {ParentComparison} from './api/training'
import {chartBase,type ChartSpec,finite} from './training-charts'
export function comparisonCharts(comparison:ParentComparison|undefined,counts:{improved:number;regressed:number}|undefined):ChartSpec[]{
 const p=comparison?.parentMetrics,c=comparison?.childMetrics,ready=!!p&&!!c&&p.rows===c.rows
 const keys=[['准确率','accuracy'],['精确率','precision'],['召回率','recall'],['F1','f1'],['Macro-F1','macro_f1'],['ROC AUC','roc_auc']] as const
 const correct=p?p.confusionMatrix[0]![0]!+p.confusionMatrix[1]![1]!:0
 const childCorrect=c?c.confusionMatrix[0]![0]!+c.confusionMatrix[1]![1]!:0
 const valid=!!counts&&Number.isInteger(counts.improved)&&Number.isInteger(counts.regressed)&&counts.improved>=0&&counts.regressed>=0&&counts.regressed<=correct&&counts.improved<=(p?.rows||0)-correct&&correct-counts.regressed+counts.improved===childCorrect
 const links=counts&&valid?[{source:'父版正确',target:'续训正确',value:correct-counts.regressed},{source:'父版错误',target:'续训正确',value:counts.improved,filter:'improved'},{source:'父版正确',target:'续训错误',value:counts.regressed,filter:'regressed'},{source:'父版错误',target:'续训错误',value:(p?.rows||0)-correct-counts.improved,filter:'errors'}].filter(l=>l.value>0):[]
 return [
 {key:'version-slope',title:'续训前后指标变化',group:'版本变化',ready,option:{...chartBase,legend:{},xAxis:{type:'category',data:['父版本','续训版本']},yAxis:{type:'value',min:0,max:1,name:'指标'},series:keys.filter(([,k])=>finite(p?.[k])&&finite(c?.[k])).map(([name,k])=>({name,type:'line',symbolSize:10,lineStyle:{width:2},data:[p?.[k],c?.[k]]}))}},
 {key:'version-flow',title:'共同测试样本判定流向',group:'版本变化',ready:ready&&links.length>0,option:{tooltip:{trigger:'item'},series:[{type:'sankey',left:12,right:95,top:30,bottom:25,emphasis:{focus:'adjacency'},nodeWidth:16,nodeGap:22,label:{fontSize:12,formatter:(p:any)=>`${p.name}\n${p.value??''}条`},lineStyle:{color:'gradient',opacity:.45},data:[...new Set(links.flatMap(l=>[l.source,l.target]))].map(name=>({name,value:links.reduce((n,l)=>n+(l.source===name||l.target===name?l.value:0),0),itemStyle:{color:name.includes('错误')?'#da9344':'#329b8c'}})),links}]}}
 ]
}
