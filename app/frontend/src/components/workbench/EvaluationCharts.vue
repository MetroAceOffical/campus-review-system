<script setup lang="ts">
import { computed } from 'vue'
import type { Metrics } from '../../api/training'
import ExperimentChart from '../experiments/ExperimentChart.vue'
const props = defineProps<{ metrics: Metrics }>()
const base = { grid: { left: 55, right: 25, top: 35, bottom: 45 }, aria: { enabled: true }, tooltip: { trigger: 'item', borderRadius: 0 } }
const matrix = computed(() => ({ ...base, tooltip: { formatter: (p: any) => `实际${p.value[1]} / 预测${p.value[0]}：${p.value[2]}条`, borderRadius: 0 }, xAxis: { type: 'category', name: '预测', data: ['非复用', '复用'] }, yAxis: { type: 'category', name: '实际', data: ['非复用', '复用'] }, visualMap: { min: 0, max: Math.max(1, ...props.metrics.confusionMatrix.flat()), show: false }, series: [{ type: 'heatmap', label: { show: true, fontSize: 24 }, data: props.metrics.confusionMatrix.flatMap((row, y) => row.map((n, x) => [x, y, n])) }] }))
const roc = computed(() => ({ ...base, xAxis: { type: 'value', name: 'FPR', min: 0, max: 1 }, yAxis: { type: 'value', name: 'TPR', min: 0, max: 1 }, series: [{ name: 'ROC', type: 'line', showSymbol: false, data: props.metrics.roc }] }))
const pr = computed(() => ({ ...base, xAxis: { type: 'value', name: 'Recall', min: 0, max: 1 }, yAxis: { type: 'value', name: 'Precision', min: 0, max: 1 }, series: [{ name: 'PR', type: 'line', showSymbol: false, data: props.metrics.pr }] }))
const format = (n: number | null | undefined) => n === null || n === undefined ? '—' : (n * 100).toFixed(2) + '%'
</script>
<template><div class="work-stats"><div v-for="([label, key]) in [['Accuracy','accuracy'],['Precision','precision'],['Recall','recall'],['F1','f1'],['Macro-F1','macro_f1'],['ROC AUC','roc_auc']]" :key="key"><span>{{ label }}</span><strong>{{ format((metrics as any)[key!]) }}</strong></div></div><p class="muted">评价 {{ metrics.rows.toLocaleString() }} 个句对</p><div class="experiment-grid"><ExperimentChart title="混淆矩阵" :option="matrix as any" /><ExperimentChart v-if="metrics.roc.length" title="ROC曲线" :option="roc as any" /><ExperimentChart v-if="metrics.pr.length" title="PR曲线" :option="pr as any" /></div></template>
