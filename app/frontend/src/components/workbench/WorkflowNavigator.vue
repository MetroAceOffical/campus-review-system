<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as datasets from '../../api/workbench'
import * as training from '../../api/training'
import { session } from '../../session'
import { workflowContext, currentDestination } from '../../workflow-context'
import { workflowStages, versionName, purposeFor } from '../../workbench-guidance'
import DatasetJourney from './DatasetJourney.vue'
const route = useRoute(), error = ref(''), expanded = ref(false)
const paths = ['/datasets', '/training', '/models', '/releases', '/reference-imports', '/references']
const visible = computed(() => paths.includes(route.path) && session.user?.role !== 'MEMBER')
let ticket = 0
watch(() => [session.user?.userId, route.path, route.query.dataset, route.query.version, route.query.run, route.query.model, route.query.modelId], async () => {
  const token = ++ticket
  if (!visible.value) return
  error.value = ''
  let id = String(route.query.dataset || ''), version = String(route.query.version || '')
  let runId = '', modelId = ''
  try {
    if (route.path === '/training' && route.query.run) { const run = await training.run(String(route.query.run)); id = run.datasetId; version = run.inputVersionId; runId = run.action === 'TRAIN' ? run.runId : ''; if (run.action === 'TRAIN' && run.status === 'COMPLETED') modelId = run.runId }
    else if ((route.path === '/models' && route.query.model) || (route.path === '/releases' && route.query.modelId)) { const model = await training.model(String(route.query.model || route.query.modelId)); id = model.datasetId; version = model.inputVersionId || (await training.run(model.runId)).inputVersionId; modelId = model.modelId; runId = model.runId }
    if (!id) return
    const data = await datasets.dataset(id)
    if (token !== ticket) return
    if (!data.versions.some(v => v.versionId === version)) version = data.versions[0]?.versionId || ''
    if (workflowContext.dataset?.datasetId !== id || workflowContext.version !== version) { workflowContext.model = undefined; workflowContext.run = undefined }
    workflowContext.dataset = data; workflowContext.version = version
    if (route.path === '/training') { workflowContext.run = runId || undefined; workflowContext.model = modelId || undefined }
    if (runId) workflowContext.run = runId
    if (modelId) workflowContext.model = modelId
  } catch (value) { if (token === ticket) { workflowContext.dataset = undefined; error.value = value instanceof Error ? value.message : '当前流程读取失败' } }
}, { immediate: true })
watch(() => session.user, () => { workflowContext.dataset = undefined; workflowContext.version = ''; workflowContext.model = undefined; workflowContext.run = undefined })
const currentVersion = computed(() => workflowContext.dataset?.versions.find(v => v.versionId === workflowContext.version))
const next = computed(() => {
  const data = workflowContext.dataset
  if (!data) return undefined
  const stages = workflowStages(data, workflowContext.version, workflowContext.model)
  const clean = stages.find(s => s.key === 'clean')
  if (clean?.status !== 'done') return { label: '继续质量评估与清洗', to: currentDestination('clean') }
  const purpose = purposeFor(data.kind, data.purpose)
  if (['LIBRARY', 'BOTH'].includes(purpose) && stages.find(s => s.key === 'library')?.status !== 'done') return { label: '继续历史新闻入库', to: currentDestination('library') }
  if (session.user?.role === 'ADMIN' && ['TRAIN', 'BOTH'].includes(purpose)) {
    const step = stages.find(s => ['prepare', 'train', 'evaluate'].includes(s.key) && s.status !== 'done')
    if (step) return { label: step.status === 'active' ? `查看${step.label}进度` : `下一步：${step.label}`, to: currentDestination(step.key) }
    if (route.path === '/models' && workflowContext.model) return { label: route.query.tab === 'prediction' ? '查看模型概览' : '下一步：试用模型预测', to: { path: '/models', query: { dataset: data.datasetId, version: workflowContext.version, model: workflowContext.model, tab: route.query.tab === 'prediction' ? 'overview' : 'prediction' } } }
    return { label: '查看模型评价', to: currentDestination('evaluate') }
  }
  return { label: '查看入库结果', to: currentDestination('library') }
})
</script>
<template>
  <section v-if="visible && workflowContext.dataset" class="workflow-context" aria-label="当前数据流程">
    <div class="workflow-context-heading"><div><span class="section-label">当前数据流程</span><strong>{{ workflowContext.dataset.name }}</strong><small v-if="currentVersion">{{ versionName(currentVersion) }}</small></div><div class="work-actions"><RouterLink class="link-button" :to="{path:'/datasets',query:{dataset:workflowContext.dataset.datasetId,version:workflowContext.version}}">返回这批数据</RouterLink><RouterLink v-if="next" class="link-button workflow-next" :to="next.to">{{ next.label }} →</RouterLink><el-button v-if="route.path !== '/datasets'" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起流程' : '查看完整流程' }}</el-button></div></div>
    <DatasetJourney v-if="expanded && route.path !== '/datasets'" :dataset="workflowContext.dataset" :version-id="workflowContext.version" compact />
  </section><p v-else-if="visible && error" class="work-error" role="alert">{{ error }}</p>
</template>
<style scoped>.workflow-context{border:1px solid var(--line);border-left:3px solid var(--el-color-primary);padding:16px 20px;background:var(--canvas);margin-bottom:20px}.workflow-context-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.workflow-context-heading>div:first-child{display:grid;gap:6px}.workflow-context strong{font-size:15px}.workflow-context small{color:var(--muted)}.workflow-next{background:var(--el-color-primary);color:white}.workflow-context :deep(.dataset-journey){margin:18px 0 0}</style>
