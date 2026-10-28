<script setup lang="ts">
import { computed } from 'vue'
import type { EChartsCoreOption } from 'echarts/core'
import ExperimentChart from '../experiments/ExperimentChart.vue'
import type { Audit, Cleaning, Progress } from '../../api/workbench'
const props = defineProps<{ audit: Audit; cleaning?: Cleaning | null; events: Progress[] }>()
function bars(values: Record<string, number>, horizontal = false): EChartsCoreOption {
  const entries = Object.entries(values).sort((a, b) => b[1] - a[1])
  return { grid: { left: horizontal ? 100 : 55, right: 20, bottom: 70, top: 35 },
    xAxis: horizontal ? { type: 'value' } : { type: 'category', data: entries.map(x => x[0]), axisLabel: { rotate: 25 } },
    yAxis: horizontal ? { type: 'category', data: entries.map(x => x[0]) } : { type: 'value', name: '记录数' },
    series: [{ type: 'bar', data: entries.map(x => x[1]), barMaxWidth: 30 }],
    dataZoom: [{ type: 'inside', ...(horizontal ? { yAxisIndex: 0 } : {}) }],
    toolbox: { show: false }, aria: { enabled: true } }
}
const fieldLabels: Record<string, string> = { text: '正文', title: '标题（可选）', id: '编号（可选）', source_institution: '来源学校（可选）', url: '来源网址（可选）', published_at: '发布日期（可选）', department: '材料部门（可选）', sentence1: '原句', sentence2: '改写句', label: '标签', source_id: '原作编号（可选）', group_id: '分组编号（可选）', label_origin: '标签来源（可选）' }
const missing = computed(() => bars(Object.fromEntries(Object.entries(props.audit.missing).filter(([key]) => key in fieldLabels).map(([key, value]) => [fieldLabels[key]!, value])))), source = computed(() => bars(props.audit.sourceDistribution, true))
const issue = computed(() => bars(props.audit.issueCounts, true)), labels = computed(() => bars(props.audit.classDistribution))
const length = computed<EChartsCoreOption>(() => {
  const values = props.audit.lengths.text?.histogram ?? props.audit.lengths.sentence1?.histogram ?? []
  return { ...bars({}), xAxis: { type: 'value', name: '字符数' }, series: [{ type: 'scatter', symbolSize: 6, data: values.map(x => [x.length, x.count]) }] }
})
const dates = computed<EChartsCoreOption>(() => ({ ...bars(props.audit.dateDistribution), xAxis: { type: 'category', data: Object.keys(props.audit.dateDistribution).sort(), axisLabel: { rotate: 25 } }, series: [{ type: 'line', data: Object.keys(props.audit.dateDistribution).sort().map(key => props.audit.dateDistribution[key]), showSymbol: false }] }))
const comparison = computed<EChartsCoreOption>(() => ({ ...bars({}), legend: { data: ['清洗前', '清洗后'] }, xAxis: { type: 'category', data: ['总记录', '结构有效', '异常记录', '精确重复'] }, series: [props.cleaning?.before, props.cleaning?.after].filter(Boolean).map((a, index) => ({ type: 'bar', name: index ? '清洗后' : '清洗前', data: [a!.totalRows, a!.validRows, a!.invalidRows, a!.duplicateRows] })) }))
</script>
<template><div class="dataset-charts">
  <ExperimentChart v-if="cleaning" title="清洗前后对比" :option="comparison" />
  <ExperimentChart title="字段缺失" :option="missing" /><ExperimentChart title="正文长度分布" :option="length" />
  <ExperimentChart v-if="Object.keys(audit.sourceDistribution).length" title="材料来源" :option="source" />
  <ExperimentChart v-if="Object.keys(audit.dateDistribution).length" title="发布时间分布" :option="dates" />
  <ExperimentChart v-if="Object.keys(audit.issueCounts).length" title="待处理问题" :option="issue" />
  <ExperimentChart v-if="Object.keys(audit.classDistribution).length" title="标签分布" :option="labels" />
</div></template>
<style scoped>.dataset-charts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}@media(max-width:1250px){.dataset-charts{grid-template-columns:minmax(0,1fr)}}</style>
