<script setup lang="ts">
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {analytics,type Metrics,type PredictionAnalytics} from '../../api/training'
import {evaluationCharts} from '../../evaluation-charts'
import ChartDeck from './ChartDeck.vue'
import PredictionResults from './PredictionResults.vue'
import EvaluationCharts from './EvaluationCharts.vue'
const props=defineProps<{runId:string;metrics:Metrics}>()
const data=ref<PredictionAnalytics>(),error=ref(''),loading=ref(false),drawer=ref(false),outcome=ref('all')
let alive=true,ticket=0
watch(()=>props.runId,async id=>{const token=++ticket;data.value=undefined;error.value='';drawer.value=false;if(!id)return;loading.value=true;try{const value=await analytics(id);if(alive&&token===ticket)data.value=value}catch(e){if(alive&&token===ticket)error.value=e instanceof Error?e.message:'读取评价统计失败'}finally{if(alive&&token===ticket)loading.value=false}},{immediate:true})
onBeforeUnmount(()=>{alive=false;ticket++})
const charts=computed(()=>evaluationCharts(props.metrics,data.value))
function select(key:string,point:any){if(data.value?.partition!=='test'||!['matrix','matrix-normalized'].includes(key)||!Array.isArray(point.value))return;const [predicted,actual]=point.value;outcome.value=actual===1?(predicted===1?'TP':'FN'):(predicted===1?'FP':'TN');drawer.value=true}
const names:Record<string,string>={TP:'正确检出',FP:'误报',TN:'正确排除',FN:'漏报'}
</script>
<template><div class="prediction-analysis" v-loading="loading"><EvaluationCharts :metrics="metrics" view="metrics"/><div class="analysis-summary"><span>{{data?.partition==='validation'?'验证集':data?.partition==='test'?'测试集':'评价数据'}} · {{metrics.rows.toLocaleString()}} 条</span><span v-if="data?.brierScore!==undefined">Brier {{data.brierScore.toFixed(4)}}</span><span v-if="data?.scoreType==='margin'">SVM间隔分数</span></div><el-alert v-if="error" :title="error" type="error" :closable="false"/><p v-if="data&&!data.available" class="muted">{{data.message}}</p><ChartDeck :charts="charts" @select="select"/><el-drawer v-model="drawer" :title="names[outcome]+' · 测试样本'" size="86%" destroy-on-close><PredictionResults v-if="drawer" :run-id="runId" action="EVALUATE" :initial-outcome="outcome"/></el-drawer></div></template>
<style scoped>.prediction-analysis :deep(.work-stats){grid-template-columns:repeat(6,minmax(0,1fr))}.prediction-analysis :deep(.work-stats strong){font-size:22px}@media(max-width:1000px){.prediction-analysis :deep(.work-stats){grid-template-columns:repeat(3,minmax(0,1fr))}}.analysis-summary{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:8px 0}</style>
