<script setup lang="ts">
import { computed,onMounted,onBeforeUnmount,ref,watch } from 'vue'
import { createExperimentState,listExperiments,type ExperimentManifest } from '../api/experiments'
import { metricNames,type MetricKey } from '../components/experiments/charts'
import OverviewCharts from '../components/experiments/OverviewCharts.vue'
import EvaluationCharts from '../components/experiments/EvaluationCharts.vue'
import TrainingCharts from '../components/experiments/TrainingCharts.vue'
import ComparisonCharts from '../components/experiments/ComparisonCharts.vue'
const {bundle,checkedAt,error,loading,refresh,cancel}=createExperimentState(),catalog=ref<ExperimentManifest[]>([]),selected=ref(''),model=ref('bert'),testSet=ref(''),metric=ref<MetricKey>('macro_f1'),tab=ref('overview'),automatic=ref(false)
let timer:ReturnType<typeof setInterval>|undefined,disposed=false
const manifest=computed(()=>bundle.value?.manifest),metrics=computed(()=>bundle.value?.metrics.sets[testSet.value]),selectedValues=computed(()=>metrics.value?.models[model.value])
async function check(){if(!selected.value||loading.value)return;await refresh(selected.value)}
onMounted(async()=>{try{const result=await listExperiments();if(disposed)return;catalog.value=result.experiments;selected.value=result.experiments[0]?.id??'';if(!selected.value)error.value='尚无已导出的实验包'}catch(failure){error.value=failure instanceof Error?failure.message:'读取实验目录失败'}})
watch(selected,id=>{if(id)void refresh(id)})
watch(manifest,next=>{if(!next)return;if(!next.testSets.some(s=>s.id===testSet.value))testSet.value=next.testSets[0]?.id??'';if(!next.models.some(m=>m.id===model.value))model.value=next.models[0]?.id??''})
watch(automatic,on=>{if(timer)clearInterval(timer);timer=on?setInterval(()=>void check(),10000):undefined})
onBeforeUnmount(()=>{disposed=true;cancel();if(timer)clearInterval(timer)})
</script>
<template><section class="panel experiment-page" v-loading="loading">
  <div class="list-filters"><el-select v-model="selected" aria-label="选择实验" class="experiment-picker"><el-option v-for="item in catalog" :key="item.id" :value="item.id" :label="item.title" /></el-select><el-button :disabled="!selected||loading" @click="check">检查更新</el-button><el-checkbox v-model="automatic">每10秒检查</el-checkbox><span class="muted">最近检查 {{ checkedAt?new Date(checkedAt).toLocaleTimeString('zh-CN'):'—' }}</span></div>
  <el-alert v-if="error" :title="error" type="warning" :closable="false" />
  <template v-if="bundle&&manifest&&metrics&&selectedValues">
    <h2>{{ manifest.title.replace('冻结', '') }}</h2><p class="muted">{{ manifest.dataset }} · {{ manifest.taskType === 'text_pair_classification' ? '文本复述分类' : manifest.taskType }} · 实验日期 {{ new Date(manifest.frozenAt).toLocaleString('zh-CN') }}</p>
    <div class="experiment-controls"><label>测试口径 <el-select v-model="testSet" aria-label="测试口径"><el-option v-for="set in manifest.testSets" :key="set.id" :value="set.id" :label="set.label" /></el-select></label><label>模型 <el-select v-model="model" aria-label="实验模型"><el-option v-for="item in manifest.models" :key="item.id" :value="item.id" :label="item.label" /></el-select></label><label>概览指标 <el-select v-model="metric" aria-label="概览指标"><el-option v-for="(label,key) in metricNames" :key="key" :value="key" :label="label" /></el-select></label></div>
    <div class="experiment-stats"><div><span>当前模型 / 样本数</span><strong>{{ manifest.models.find(m=>m.id===model)?.label }} / {{ metrics.n }}</strong></div><div><span>Macro-F1</span><strong>{{ selectedValues.macro_f1.toFixed(8) }}</strong></div><div><span>Accuracy</span><strong>{{ selectedValues.accuracy.toFixed(8) }}</strong></div><div><span>ROC AUC</span><strong>{{ selectedValues.roc_auc.toFixed(8) }}</strong></div></div>
    <el-tabs v-model="tab"><el-tab-pane label="总体表现" name="overview" /><el-tab-pane label="分类评估" name="evaluation" /><el-tab-pane label="训练历史" name="training" /><el-tab-pane label="配置比较" name="comparison" /></el-tabs>
    <OverviewCharts v-if="tab==='overview'" :bundle="bundle" :test-set="testSet" :metric="metric" /><EvaluationCharts v-else-if="tab==='evaluation'" :bundle="bundle" :test-set="testSet" :model="model" /><TrainingCharts v-else-if="tab==='training'" :bundle="bundle" :model="model" /><ComparisonCharts v-else :bundle="bundle" :model="model" />
    <el-collapse class="experiment-provenance"><el-collapse-item title="实验信息" name="provenance"><p>数据版本：{{ manifest.datasetRevision }}</p><p>更新时间：{{ new Date(manifest.updatedAt).toLocaleString('zh-CN') }} · 参数配置：{{ bundle.search.configurations.length }}组</p></el-collapse-item></el-collapse>
  </template>
</section></template>
