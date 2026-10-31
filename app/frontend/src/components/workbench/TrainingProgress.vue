<script setup lang="ts">
import { computed,ref } from 'vue'
import ChartDeck from './ChartDeck.vue'
import PredictionAnalysis from './PredictionAnalysis.vue'
const showValidation=ref(false)
import {trainingCharts} from '../../training-charts'
import { session } from '../../session'
import type { ComputeEvent, ComputeRun } from '../../api/training'
import { actionNames, stateNames, terminal, modelNames } from '../../api/training'
import ExperimentChart from '../experiments/ExperimentChart.vue'
const props = defineProps<{ run: ComputeRun; events: ComputeEvent[] }>()
defineEmits<{ cancel: [] }>()
const latest = computed(() => [...props.events].reverse().find(event => event.data.stage !== 'HEARTBEAT')?.data)
const counts = computed(() => [...props.events].reverse().find(event => event.data.processed !== undefined && event.data.total !== undefined)?.data)
const epoch = computed(() => [...props.events].reverse().find(event => event.data.epoch !== undefined && ['TRAINING','EPOCH'].includes(event.data.stage))?.data)

const progress = computed(() => counts.value?.total ? Math.round((counts.value.processed ?? 0) / counts.value.total * 100) : null)
const generation = computed(() => props.events.filter(e => e.data.accepted !== undefined))
const generationCount = computed(() => generation.value.at(-1)?.data)
const samplePreview = computed(() => [...props.events].reverse().find(e => e.data.preview)?.data.preview)
const base = { grid: { left: 55, right: 22, top: 45, bottom: 48 }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 4 }], aria: { enabled: true }, tooltip: { trigger: 'axis', borderRadius: 0 } }
const charts=computed(()=>trainingCharts(props.events,props.run.result?.history||[]))
const generationCurve = computed(() => ({ ...base, legend: { data: ['合格改写', '隔离段落'] }, xAxis: { type: 'category', data: generation.value.map(e => e.data.processed) }, yAxis: { type: 'value' }, series: [{ name: '合格改写', type: 'line', showSymbol: false, data: generation.value.map(e => e.data.accepted) }, { name: '隔离段落', type: 'line', showSymbol: false, data: generation.value.map(e => e.data.quarantined) }] }))
</script>
<template>
  <section class="work-panel" aria-live="polite"><div class="work-heading"><div><h2>{{ run.options.name || actionNames[run.action] }}</h2><span class="muted">{{ actionNames[run.action] }}<template v-if="run.options.family"> · {{ modelNames[run.options.family] }}</template> · {{ run.runId.slice(0, 8) }}</span></div><el-tag>{{ stateNames[run.status] || run.status }}</el-tag></div>
    <div class="work-stats"><div><span>当前阶段</span><strong class="stage-value">{{ stateNames[latest?.stage || run.status] || latest?.stage }}</strong></div><div><span>已处理 / 总量</span><strong>{{ counts?.processed?.toLocaleString() ?? '—' }} <small>/ {{ counts?.total?.toLocaleString() ?? '—' }}</small></strong></div><div><span>轮数</span><strong>{{ epoch?.epoch ?? '—' }} <small v-if="epoch?.epochs || run.options.parameters?.epochs">/ {{ epoch?.epochs ?? run.options.parameters?.epochs }}</small></strong></div></div>
    <el-progress v-if="progress !== null" :percentage="Math.min(100, progress)" />
    <p v-if="run.error" class="work-error" role="alert">{{ run.error }}</p><p v-if="latest?.message">{{ latest.message }}</p>
    <el-button v-if="!terminal(run.status) && (session.user?.role === 'ADMIN' || !['PREPARE','GENERATE','TRAIN'].includes(run.action))" @click="$emit('cancel')">取消任务</el-button>
    <template v-if="run.action === 'GENERATE'"><div class="work-stats"><div><span>处理原稿</span><strong>{{ generationCount?.originals ?? '—' }}</strong></div><div><span>合格改写</span><strong>{{ generationCount?.accepted ?? '—' }}</strong></div><div><span>隔离 / 复用</span><strong>{{ generationCount?.quarantined ?? '—' }} <small>/ {{ generationCount?.reused ?? '—' }}</small></strong></div></div><ExperimentChart v-if="generation.length" title="样本准备进度" :option="generationCurve as any" /><div v-if="samplePreview" class="sample-compare"><div><h3>原文</h3><p>{{ samplePreview.source }}</p></div><div><h3>改写 · {{ samplePreview.accepted ? '检查通过' : '待重试或隔离' }}</h3><p>{{ samplePreview.rewritten }}</p><span v-if="samplePreview.reasons?.length" class="muted">{{ samplePreview.reasons.join(' / ') }}</span></div></div></template>
    <ChartDeck v-if="run.action==='TRAIN'" :charts="charts"/><details v-if="run.action==='TRAIN' && run.status==='COMPLETED' && run.result?.validation" @toggle="showValidation=($event.target as HTMLDetailsElement).open"><summary>验证集得分与错误分析</summary><PredictionAnalysis v-if="showValidation" :run-id="run.runId" :metrics="run.result.validation"/></details>
    <details><summary>阶段日志（最近{{ events.length }}条）</summary><ol class="work-events"><li v-for="event in events.slice(-60)" :key="event.sequence">{{ stateNames[event.data.stage] || event.data.stage }} <span v-if="event.data.processed !== undefined">{{ event.data.processed }} / {{ event.data.total }}</span><span v-if="event.data.loss !== undefined"> · Loss {{ event.data.loss.toFixed(5) }}</span><span v-if="event.data.message"> · {{ event.data.message }}</span></li></ol></details>
  </section>
</template>
<style scoped>.sample-compare{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}.sample-compare>div{border:1px solid var(--line);padding:15px;min-width:0}.sample-compare h3{font-size:14px}.sample-compare p{font-size:13px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:750px){.sample-compare{grid-template-columns:1fr}}</style>
