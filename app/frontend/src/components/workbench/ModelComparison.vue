<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Model } from '../../api/training'
import { modelNames } from '../../api/training'
import ExperimentChart from '../experiments/ExperimentChart.vue'
import ChartDeck from './ChartDeck.vue'
import ExperimentAnalysis from './ExperimentAnalysis.vue'
import {modelCharts} from '../../experiment-charts'
const props = defineProps<{ models: Model[] }>()
defineEmits<{ remove: [id: string]; clear: [] }>()
const selectedGroup = ref('')
const groups = computed(() => {
  const grouped = new Map<string, { key: string; name: string; models: Model[] }>()
  for (const model of props.models) {
    const manifest = model.manifest
    const key = manifest.inputSha256 && manifest.preparationSha256 ? `${manifest.inputSha256}:${manifest.preparationSha256}:${manifest.validationRows}` : `unknown:${model.modelId}`
    if (!grouped.has(key)) grouped.set(key, { key, name: key.startsWith('unknown:') ? `划分未记录 · ${model.name}` : `划分${grouped.size + 1}`, models: [] })
    grouped.get(key)!.models.push(model)
  }
  return [...grouped.values()]
})
watch(groups, value => { if (!value.some(group => group.key === selectedGroup.value)) selectedGroup.value = value[0]?.key ?? '' }, { immediate: true })
const comparisonTab=ref('models')
const groupModels = computed(() => groups.value.find(group => group.key === selectedGroup.value)?.models ?? [])
const groupName = (model: Model) => groups.value.find(group => group.models.some(row => row.modelId === model.modelId))?.name ?? '—'
const format = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : `${(value * 100).toFixed(2)}%`
const base = { grid: { left: 55, right: 20, top: 45, bottom: 60 }, tooltip: { trigger: 'axis', borderRadius: 0 }, aria: { enabled: true }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 3 }] }
const metrics = computed(() => ({ ...base, legend: { data: ['Accuracy', 'Precision', 'Recall', 'Macro-F1'] }, xAxis: { type: 'category', data: groupModels.value.map(model => `${model.family.toUpperCase()} · v${model.versionNumber||1} · ${model.modelId.slice(0,6)}`) }, yAxis: { type: 'value', min: 0, max: 1 }, series: [['Accuracy', 'accuracy'], ['Precision', 'precision'], ['Recall', 'recall'], ['Macro-F1', 'macro_f1']].map(([name, key]) => ({ name, type: 'bar', data: groupModels.value.map(model => model.manifest.validation[key as 'accuracy' | 'precision' | 'recall' | 'macro_f1']) })) }))
const time = computed(() => ({ ...base, tooltip: { trigger: 'item', borderRadius: 0, formatter: (point: any) => `${point.value[2]}\n训练 ${point.value[0].toFixed(2)}秒\n验证Macro-F1 ${format(point.value[1])}` }, xAxis: { type: 'value', name: '训练耗时（秒）', min: 0 }, yAxis: { type: 'value', name: '验证Macro-F1', min: 0, max: 1 }, series: [{ name: '模型', type: 'scatter', symbolSize: 15, data: groupModels.value.filter(model => Number.isFinite(model.manifest.elapsedSeconds) && Number.isFinite(model.manifest.validation.macro_f1)).map(model => [model.manifest.elapsedSeconds, model.manifest.validation.macro_f1, model.name]) }] }))
</script>
<template>
  <section v-if="models.length" class="work-panel"><div class="work-heading"><div><h2>模型比较 · {{ models.length }} / 6</h2><span class="muted">验证指标 · {{ groups.length }}个数据划分</span></div><el-button @click="$emit('clear')">清空比较</el-button></div>
    <el-table :data="models" row-key="modelId"><el-table-column prop="name" label="模型" min-width="160" /><el-table-column label="算法" min-width="130"><template #default="{ row }">{{ modelNames[row.family] }}</template></el-table-column><el-table-column label="数据 / 划分" min-width="160"><template #default="{ row }"><RouterLink :to="`/datasets?dataset=${row.datasetId}`">{{ row.datasetName || row.datasetId.slice(0, 8) }}</RouterLink> · {{ groupName(row) }}</template></el-table-column><el-table-column prop="manifest.trainRows" label="训练数" /><el-table-column prop="manifest.validationRows" label="验证数" /><el-table-column label="验证Macro-F1" width="140"><template #default="{ row }">{{ format(row.manifest.validation.macro_f1) }}</template></el-table-column><el-table-column label="训练耗时" width="120"><template #default="{ row }">{{ row.manifest.elapsedSeconds.toFixed(2) }}秒</template></el-table-column><el-table-column label="操作" width="80"><template #default="{ row }"><el-button link @click="$emit('remove', row.modelId)">移除</el-button></template></el-table-column></el-table>
    <details><summary>训练参数与数据身份</summary><div v-for="model in models" :key="model.modelId"><h3>{{ model.name }}</h3><p class="work-params">输入SHA {{ model.manifest.inputSha256 ?? '—' }}<br>划分SHA {{ model.manifest.preparationSha256 ?? '—' }}</p><pre class="work-params">{{ JSON.stringify(model.manifest.parameters, null, 2) }}</pre></div></details>
    <p v-if="models.length < 2" class="muted">再勾选一个模型开始比较。</p>
    <template v-else><el-select v-if="groups.length > 1" v-model="selectedGroup" aria-label="比较数据划分"><el-option v-for="group in groups" :key="group.key" :value="group.key" :label="`${group.name} · ${group.models.length}模型`" /></el-select><el-tabs v-model="comparisonTab"><el-tab-pane label="模型效果对比" name="models"/><el-tab-pane label="调参分析" name="parameters"/></el-tabs><ChartDeck v-if="comparisonTab==='models'" :charts="modelCharts(groupModels)"/><ExperimentAnalysis v-else :models="models"/></template>
  </section>
</template>
