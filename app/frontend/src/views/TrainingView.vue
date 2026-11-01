<script setup lang="ts">
import RecordPagination from '../components/RecordPagination.vue'
import {trainingSelection} from '../bundle-navigation'
const dataSize = ref(12), runSize = ref(20)
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as datasets from '../api/workbench'
import * as api from '../api/training'
import type { ComputeRun, ComputeEvent, Preparation, Model } from '../api/training'
import type { Dataset, Detail } from '../api/workbench'
import AppIcon from '../components/AppIcon.vue'
import { activeFlow } from '../flow-session'
import { getFlow } from '../api/flows'
import { workflowContext } from '../workflow-context'
import { versionName } from '../workbench-guidance'
import TrainingProgress from '../components/workbench/TrainingProgress.vue'
import ExperimentChart from '../components/experiments/ExperimentChart.vue'
import NewsSampleReport from '../components/workbench/NewsSampleReport.vue'
import FormalTrainingProgress from '../components/workbench/FormalTrainingProgress.vue'
import AutomaticPipeline from '../components/workbench/AutomaticPipeline.vue'
const route = useRoute(), router = useRouter(), error = ref(''), busy = ref(false), q = ref(''), dataPage = ref(1), dataTotal = ref(0), dataItems = ref<Dataset[]>([])
const recoveredPreparation = ref<ComputeRun>(),parentModel=ref<Model>(),parentBundleId=ref(''),focusBundleId=ref(String(route.query.bundle||'')),parentWidths=ref<Record<string,number>>({})
const datasetId = ref(''), versionId = ref(''), detail = ref<Detail | null>(null), preparationId = ref(''), current = ref<ComputeRun | null>(null), events = ref<ComputeEvent[]>([])
watch(detail, data => { if (data && workflowContext.dataset?.datasetId === data.datasetId) workflowContext.dataset = data })
watch(current, run => { if (run?.action === 'TRAIN' && run.status === 'COMPLETED' && workflowContext.dataset?.datasetId === run.datasetId && workflowContext.version === run.inputVersionId) workflowContext.model = run.runId })
const followedRun = ref(''), followedAttempt = ref('')
const activeTab = ref(typeof route.query.run === 'string' ? 'tasks' : String(route.query.tab || 'new')), creationStep = ref(0), executionMode = ref('guided')
const neural = computed(() => selectedModels.value.some(f => ['cnn','bilstm','bert'].includes(f)))
const classical = computed(() => selectedModels.value.some(f => ['lr','svm','rf'].includes(f)))
function parameterVisible(key: string) { if(parentModel.value && key==='width')return false; if (['C','max_iter'].includes(key)) return selectedModels.value.some(f => ['lr','svm'].includes(f)); if (['n_estimators','max_depth','min_samples_leaf'].includes(key)) return selectedModels.value.includes('rf'); if (['width','dropout'].includes(key)) return selectedModels.value.some(f => ['cnn','bilstm'].includes(f)); return neural.value }
function continueSetup() { activeTab.value = 'new'; creationStep.value = preparation.value?.trainReady ? 2 : detail.value?.kind === 'NEWS' && preparation.value ? 1 : 0; void router.replace({query:{dataset:datasetId.value,version:versionId.value,tab:'new',step:String(creationStep.value)}}) }
const runPage = ref(1), runTotal = ref(0), history = ref<ComputeRun[]>([]), selectedModels = ref<string[]>([...api.sixFamilies])
const partition = reactive({ train: 80, validation: 10, test: 10, seed: 20261028 }), name = ref('')
const generationConfig = reactive({ max_originals: 0, segment_characters: 360, min_characters: 64, variants: 1, negative_candidates: 40, negatives_per_positive: 1, attempts: 2, device: 'cuda', reuse_existing: true })
const config = reactive({ C: 1, max_iter: 1000, class_weight: 'none', n_estimators: 100, max_depth: 20, min_samples_leaf: 1, epochs: 3, batch_size: 32, learning_rate: .001, bert_learning_rate: .00002, width: 64, dropout: .2, max_length: 128, patience: 2, weight_decay: .01, gradient_accumulation: 1, device: 'cuda' })
const pipelineModels = computed(() => selectedModels.value.map(family => { const parameters: Record<string, unknown> = { ...config, seed: partition.seed, device: ['lr', 'svm', 'rf'].includes(family) ? 'cpu' : config.device, learning_rate: family === 'bert' ? config.bert_learning_rate : config.learning_rate };if(parentWidths.value[family])parameters.width=parentWidths.value[family]; delete parameters.bert_learning_rate; return { family, parameters } }))
const pipelinePreparation = computed(() => ({ seed: partition.seed, ratios: [partition.train / 100, partition.validation / 100, partition.test / 100] }))
let timer: ReturnType<typeof setInterval> | undefined, stream: EventSource | undefined, generation = 0, alive = true, refreshing = false
const cleanVersions = computed(() => detail.value?.versions.filter(v => v.stage === 'CLEAN' && v.status === 'READY') ?? [])
const preparations = computed(() => [...(recoveredPreparation.value ? [recoveredPreparation.value] : []), ...(detail.value?.runs as ComputeRun[] ?? []).filter(r => r.runId !== recoveredPreparation.value?.runId)].filter(run => run.datasetId === datasetId.value && ['PREPARE', 'GENERATE'].includes(run.action) && run.status === 'COMPLETED' && run.inputVersionId === versionId.value))
const preparation = computed(() => preparations.value.find(r => r.runId === preparationId.value)?.result as Preparation | undefined)
const distribution = computed(() => ({ tooltip: { trigger: 'axis', borderRadius: 0 }, legend: {}, grid: { left: 45, right: 20, bottom: 35 }, xAxis: { type: 'category', data: ['训练', '验证', '测试', '校准'] }, yAxis: { type: 'value' }, series: ['0', '1'].map(label => ({ name: label === '0' ? '非复用' : '复用', type: 'bar', stack: 'labels', data: ['train', 'validation', 'test', 'calibration'].map(key => preparation.value?.partitions[key]?.labels[label] ?? 0) })) }))
function failure(value: unknown) { error.value = value instanceof Error ? value.message : '操作失败，请重试' }
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task() } catch (value) { failure(value) } finally { busy.value = false } }
async function loadData() { const result = await datasets.datasets(dataPage.value, q.value, false, dataSize.value); dataItems.value = result.items; dataTotal.value = result.total }
async function loadHistory() { const result = await api.runs(runPage.value, '', '', runSize.value); history.value = result.items; runTotal.value = result.total }
async function chooseDataset() { if (!datasetId.value) return; detail.value = await datasets.dataset(datasetId.value); if (!cleanVersions.value.some(v => v.versionId === versionId.value)) versionId.value = cleanVersions.value[0]?.versionId ?? ''; chooseVersion(); name.value = `${detail.value.name.slice(0, 70)}实验` }
async function recoverPreparation(id: string | undefined) { if (!id || preparations.value.some(r => r.runId === id)) return; const run=await api.run(id); if (run.datasetId===datasetId.value && run.inputVersionId===versionId.value && ['PREPARE','GENERATE'].includes(run.action) && run.status==='COMPLETED') recoveredPreparation.value=run }
function chooseVersion() { preparationId.value = preparations.value[0]?.runId ?? '' }
function rememberSelection() { return router.replace({query:trainingSelection({dataset:datasetId.value,version:versionId.value,preparation:preparationId.value,step:creationStep.value,parentBundle:parentBundleId.value,parentModel:parentModel.value?.modelId})}) }
async function chooseDataFromForm() { await chooseDataset(); await rememberSelection() }
function chooseVersionFromForm() { chooseVersion(); void rememberSelection() }

function stop() { stream?.close(); stream = undefined; if (timer) clearInterval(timer); timer = undefined }
function consume(incoming: ComputeEvent[]) { const known = new Set(events.value.map(e => e.sequence)); events.value = [...events.value, ...incoming.filter(e => !known.has(e.sequence))].slice(-1000) }
function followRun(id: string) { followedRun.value = id }
watch([activeTab, busy, followedRun], ([tab, working, id]) => { if (tab === 'tasks' && !working && id && id !== current.value?.runId && id !== followedAttempt.value) { followedAttempt.value = id; void perform(() => viewRun(id, false)) } })
async function viewRun(id: string, navigate = true) {
  stop(); if (navigate) activeTab.value = 'tasks'; const token = ++generation; current.value = await api.run(id); if (token !== generation || !alive) return
  const viewed = current.value
  if(focusBundleId.value){
    const bundle=await api.bundle(focusBundleId.value);if(token!==generation||!alive)return
    if(!bundle.state.steps.some(step=>step.runId===id)){focusBundleId.value='';followedRun.value='';followedAttempt.value='';workflowContext.bundle=undefined}
  }
  if (detail.value?.datasetId !== viewed.datasetId || versionId.value !== viewed.inputVersionId) { datasetId.value = viewed.datasetId; versionId.value = viewed.inputVersionId; await chooseDataset(); if (token !== generation || !alive) return }
  if (viewed.status === 'COMPLETED' && ['PREPARE', 'GENERATE'].includes(viewed.action)) preparationId.value = viewed.runId
  else if (viewed.options.preparationId) { await recoverPreparation(viewed.options.preparationId); preparationId.value = viewed.options.preparationId }
  events.value = []; let batch: ComputeEvent[]; do { batch = await api.events(id, events.value.at(-1)?.sequence ?? 0); if (token !== generation || !alive) return; consume(batch) } while (batch.length === 500)
  void router.replace({ query: { dataset: viewed.datasetId, version: viewed.inputVersionId, run: id, tab: 'tasks',...(focusBundleId.value?{bundle:focusBundleId.value}:{}) } })
  if (api.terminal(current.value.status)) return
  const refresh = async () => {
    if (refreshing || !alive || token !== generation) return; refreshing = true
    try {
      const [run, incoming] = await Promise.all([api.run(id), api.events(id, events.value.at(-1)?.sequence ?? 0)])
      if (!alive || token !== generation) return; current.value = run; consume(incoming)
      if (api.terminal(run.status)) { stop(); await loadHistory(); if (detail.value?.datasetId === run.datasetId) { detail.value = await datasets.dataset(run.datasetId); if (['PREPARE', 'GENERATE'].includes(run.action) && run.status === 'COMPLETED') preparationId.value = run.runId } }
    } catch (value) { failure(value) } finally { refreshing = false }
  }
  timer = setInterval(() => void refresh(), 2500)
  stream = new EventSource(`/api/workbench/runs/${id}/stream?after=${events.value.at(-1)?.sequence ?? 0}`)
  stream.addEventListener('progress', event => { if (token === generation && alive) { const e = event as MessageEvent; consume([{ sequence: Number(e.lastEventId), data: JSON.parse(e.data) }]) } })
  stream.addEventListener('snapshot', event => { if (token === generation && api.terminal(JSON.parse((event as MessageEvent).data).status)) void refresh() })
  stream.onerror = () => { if (token === generation) { stream?.close(); stream = undefined } }
}
async function prepare() { await perform(async () => {
  if (!datasetId.value || !versionId.value) throw new Error('请选择数据集和清洗版本')
  if (partition.train + partition.validation + partition.test !== 100) throw new Error('三个划分比例合计须为100%')
  const run = await api.start({ action: 'PREPARE', datasetId: datasetId.value, versionId: versionId.value, parameters: { ratios: [partition.train / 100, partition.validation / 100, partition.test / 100], seed: partition.seed } })
  await loadHistory(); await viewRun(run.runId)
}) }
async function advancePreparation(){
  if(!preparation.value){await prepare();return}
  creationStep.value=preparation.value.trainReady?2:1
  await rememberSelection()
}
async function train() { await perform(async () => {
  if (!preparation.value?.trainReady) throw new Error('请选择可训练的样本划分')
  if(parentModel.value&&!parentBundleId.value)throw new Error('该历史单模型不属于完整六模型组，请新建六模型组训练')
  const created=await api.startPipeline({datasetId:datasetId.value,versionId:versionId.value,preparationId:preparationId.value,name:name.value,models:pipelineModels.value,evaluate:true,parentPipelineId:parentBundleId.value||undefined})
  stop();generation++;current.value=null;events.value=[];followedRun.value='';followedAttempt.value='';focusBundleId.value=created.pipelineId;activeTab.value='tasks';await router.replace({query:{dataset:datasetId.value,version:versionId.value,bundle:created.pipelineId,tab:'tasks'}})
}) }
async function generateSamples(resume?: ComputeRun) { await perform(async () => {
  const source = resume?.options.preparationId ?? preparationId.value
  if (!source) throw new Error('请先选择新闻分组版本')
  const parameters = resume?.options.parameters ?? { ...generationConfig, seed: partition.seed }
  const result = await api.start({ action: 'GENERATE', datasetId: resume?.datasetId ?? datasetId.value, versionId: resume?.inputVersionId ?? versionId.value, preparationId: source, parameters, ...(resume ? { resumeRunId: resume.runId } : {}), name: '新闻原稿自动准备句对' })
  await loadHistory(); await viewRun(result.runId)
}) }
async function copyRun(run: ComputeRun) { activeTab.value = 'new'; creationStep.value = 2; datasetId.value = run.datasetId; versionId.value = run.inputVersionId; await chooseDataset(); await recoverPreparation(run.options.preparationId); preparationId.value = run.options.preparationId ?? preparationId.value; selectedModels.value = [...api.sixFamilies]; Object.assign(config, run.options.parameters ?? {}); if (run.options.family === 'bert') config.bert_learning_rate = Number(run.options.parameters?.learning_rate ?? .00002); name.value = (run.options.name ?? name.value).slice(0, 80) + ' 调参' }
async function cancel() { if (current.value) { await datasets.cancel(current.value.runId); await viewRun(current.value.runId) } }

let initialized = false
async function restoreRoute() {
  const savedFlow=route.query.flow?await getFlow(String(route.query.flow)):undefined
  const parent=String(route.query.parentModel || savedFlow?.context.parentModelId || '')
  const changedParent=!!parent&&parentModel.value?.modelId!==parent
  if(changedParent){parentModel.value=await api.model(parent);selectedModels.value=[...api.sixFamilies];parentBundleId.value=(parentModel.value as Model & {bundleId?:string}).bundleId||'';Object.assign(config,parentModel.value.manifest.parameters);if(parentModel.value.family==='bert')config.bert_learning_rate=Number(parentModel.value.manifest.parameters.learning_rate);executionMode.value='guided'}
  if(!parent){parentModel.value=undefined;parentBundleId.value=String(route.query.parentBundle||'')}
  parentWidths.value={}
  if(parentBundleId.value){const previous=await api.bundle(parentBundleId.value);const members=await Promise.all(previous.state.models.map(m=>api.model(m.modelId)));parentWidths.value=Object.fromEntries(members.filter(m=>['cnn','bilstm'].includes(m.family)).map(m=>[m.family,Number(m.manifest.parameters.width||64)]));if(changedParent)config.learning_rate=Number(members.find(m=>m.family==='cnn')?.manifest.parameters.learning_rate??.001)}
  const focus=String(route.query.bundle||'')
  if(focus!==focusBundleId.value){
    focusBundleId.value=focus;followedRun.value='';followedAttempt.value=''
    if(!focus){workflowContext.bundle=undefined;if(route.query.tab==='new'&&!route.query.run){stop();generation++;current.value=null;events.value=[];workflowContext.run=undefined;workflowContext.model=undefined}}
  }

  if (typeof route.query.run === 'string') {
    if (current.value?.runId !== route.query.run) await viewRun(route.query.run)
    activeTab.value = 'tasks'
    return
  }
  const id = String(route.query.dataset || ''), version = String(route.query.version || '')
  if (id && (datasetId.value !== id || versionId.value !== version || !detail.value)) { datasetId.value = id; versionId.value = version; await chooseDataset() }
  const selectedPreparation=String(route.query.preparation||savedFlow?.context.preparationId||'')
  if(selectedPreparation){await recoverPreparation(selectedPreparation);if(preparations.value.some(p=>p.runId===selectedPreparation))preparationId.value=selectedPreparation}
  activeTab.value = String(route.query.tab || 'new')
  creationStep.value = Math.max(0,Math.min(2,Number(route.query.step) || 0))
}
let restoredPath = ''
watch(() => [route.fullPath, busy.value], () => { if (initialized && !busy.value && restoredPath !== route.fullPath) { restoredPath = route.fullPath; void perform(restoreRoute) } })
onMounted(() => void perform(async () => { await Promise.all([loadData(), loadHistory()]); await restoreRoute(); restoredPath = route.fullPath; initialized = true }))
onBeforeUnmount(() => { alive = false; generation++; stop() })
</script>
<template>
  <p v-if="error" role="alert" class="work-error">{{ error }}</p>
  <div class="page-toolbar"><p class="muted">选择数据、准备样本并训练；每项任务的进度与结果独立保存。</p><el-button v-if="!route.query.flow" type="primary" @click="activeTab = 'new'; creationStep = 0; router.replace({query:{dataset:datasetId,version:versionId,tab:'new',step:'0'}})"><AppIcon name="train" :size="17" />　新建训练</el-button></div>
  <el-tabs v-model="activeTab" class="workspace-tabs"><el-tab-pane label="新建训练" name="new"><div v-if="!route.query.flow" class="creation-steps" aria-label="创建训练步骤"><button v-for="(label,index) in ['选择数据','准备样本','配置模型与启动']" :key="label" :class="{ selected: creationStep === index }" @click="creationStep = index; rememberSelection()"><span>{{ index+1 }}</span>{{ label }}<AppIcon name="arrow" :size="15" /></button></div>
  <section v-show="creationStep === 0" class="work-panel"><div class="work-heading"><div><h2>选择训练数据</h2><span class="muted">选定清洗版本，先准备样本，再配置模型。</span></div><RouterLink :to="{path:'/datasets',query:{dataset:datasetId,version:versionId}}" class="link-button">上传与清洗数据</RouterLink></div>
    <div class="work-search"><el-input v-model="q" placeholder="搜索数据集" aria-label="搜索训练数据集" @change="dataPage = 1; perform(loadData)" /><el-button @click="perform(loadData)">搜索</el-button><RecordPagination v-model:current-page="dataPage" v-model:page-size="dataSize" :total="dataTotal" @change="perform(loadData)" /></div>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="数据集"><el-select v-model="datasetId" aria-label="训练数据集" @change="perform(chooseDataFromForm)"><el-option v-for="item in dataItems" :key="item.datasetId" :label="`${item.name} · ${item.kind === 'NEWS' ? '新闻' : '句对'}`" :value="item.datasetId" /><el-option v-if="detail && !dataItems.some(d => d.datasetId === detail!.datasetId)" :label="detail.name" :value="detail.datasetId" /></el-select></el-form-item><el-form-item label="清洗版本"><el-select v-model="versionId" aria-label="训练清洗版本" @change="chooseVersionFromForm"><el-option v-for="version in cleanVersions" :key="version.versionId" :label="versionName(version)" :value="version.versionId" /></el-select></el-form-item><el-form-item label="随机种子"><el-input-number v-model="partition.seed" :min="0" :max="2147483647" :precision="0" /></el-form-item></div>
    <details open><summary>样本分组与划分</summary><div class="work-grid"><el-form-item v-for="(label, key) in { train: '训练集 %', validation: '验证集 %', test: '测试集 %' }" :key="key" :label="label"><el-input-number v-model="partition[key]" :min="1" :max="98" :precision="0" /></el-form-item></div><p class="muted">按来源、事件及相同句子归组；已有独立分区保持隔离。</p><el-button v-if="preparation" :disabled="!versionId || busy" @click="prepare">重新划分样本</el-button></details>
    <el-form-item label="样本版本"><el-select v-model="preparationId" aria-label="样本划分"><el-option v-for="run in preparations" :key="run.runId" :value="run.runId" :label="`${run.runId.slice(0, 8)} · ${run.result?.trainReady ? '可训练' : run.action === 'PREPARE' && detail?.kind === 'NEWS' ? '新闻分组与段落池' : '类别待补充'}`" /></el-select></el-form-item></el-form>
    <template v-if="preparation"><div class="work-stats"><div><span>原始记录</span><strong>{{ preparation.inputRows.toLocaleString() }}</strong></div><div><span>独立分组</span><strong>{{ preparation.groups.toLocaleString() }}</strong></div><div><span>{{ preparation.requiresLabels ? '待准备标签的段落' : '可训练样本' }}</span><strong>{{ (preparation.requiresLabels ? preparation.segments : preparation.outputRows ?? preparation.inputRows).toLocaleString() }}</strong></div></div>
    <el-table :data="Object.entries(preparation.partitions).map(([name, value]) => ({ name: ({train:'训练',validation:'验证',test:'测试',calibration:'校准'} as Record<string,string>)[name], ...value }))"><el-table-column prop="name" label="分区" /><el-table-column prop="rows" label="记录数" /><el-table-column prop="groups" label="组数" /><el-table-column label="类别"><template #default="{row}">{{ Object.entries(row.labels).map(([k,v]) => `${k}: ${v}`).join(' / ') }}</template></el-table-column></el-table>
    <ExperimentChart v-if="!preparation.requiresLabels" title="划分类别分布" :option="distribution as any" /><p v-if="preparation.requiresLabels">新闻分组已保存，可开始自动准备句对。</p><p v-else-if="!preparation.trainReady" class="work-error">类别不足的分区：{{ preparation.missingClassPartitions.join('、') }}</p></template>
  <div class="work-actions"><el-button type="primary" :loading="busy" :disabled="!versionId" @click="advancePreparation">{{ preparation?.trainReady ? '配置模型' : '准备样本' }}</el-button><span class="muted">{{ versionId ? '沿用本次数据和样本版本继续。' : '先选择已清洗数据；原始文件可在数据中心清洗。' }}</span></div></section>
  <section v-if="detail?.kind === 'NEWS'" v-show="creationStep === 1" class="work-panel"><div class="work-heading"><div><h2>新闻原稿自动准备训练样本</h2><span class="muted">选择新闻分组版本，自动完成改写、检查、负例准备与样本保存。</span></div></div><el-form label-position="top"><div class="work-grid"><el-form-item label="处理原稿数（0为全部）"><el-input-number v-model="generationConfig.max_originals" :min="0" :max="100000" :precision="0" /></el-form-item><el-form-item label="每段改写数量"><el-input-number v-model="generationConfig.variants" :min="1" :max="4" :precision="0" /></el-form-item><el-form-item label="执行设备"><el-select v-model="generationConfig.device"><el-option value="cuda" label="GPU / CUDA" /><el-option value="cpu" label="CPU" /></el-select></el-form-item></div><details><summary>样本准备参数</summary><div class="work-grid"><el-form-item label="段落窗口字数"><el-input-number v-model="generationConfig.segment_characters" :min="128" :max="512" :precision="0" /></el-form-item><el-form-item label="最少有效字数"><el-input-number v-model="generationConfig.min_characters" :min="32" :max="256" :precision="0" /></el-form-item><el-form-item label="负例候选数"><el-input-number v-model="generationConfig.negative_candidates" :min="5" :max="200" :precision="0" /></el-form-item><el-form-item label="每个正例对应负例数"><el-input-number v-model="generationConfig.negatives_per_positive" :min="1" :max="4" :precision="0" /></el-form-item><el-form-item label="最多尝试次数"><el-input-number v-model="generationConfig.attempts" :min="1" :max="4" :precision="0" /></el-form-item></div><el-checkbox v-model="generationConfig.reuse_existing">复用原文与检查均匹配的已有改写</el-checkbox></details></el-form><div class="work-actions"><el-button type="primary" :loading="busy" :disabled="!preparation?.requiresLabels" @click="generateSamples()">自动准备训练样本</el-button><span class="muted">完成后点击“继续配置”选择生成样本并训练。</span></div></section>
  <section v-if="creationStep === 1" class="work-panel"><div class="stage-title"><AppIcon name="data" /><h2>样本准备说明</h2></div><p class="section-intro">{{ detail?.kind === 'NEWS' ? '系统将新闻整理为原文、改写和非复用对照，并保存检查结果。' : '带标签句对完成分组划分后，即可选择模型训练。' }}</p><p>当前样本：{{ preparation?.trainReady ? '可训练' : preparation ? '仍需准备标签句对' : '尚未分组划分' }}</p><div class="work-actions"><el-button @click="creationStep = 0; rememberSelection()">返回数据与划分</el-button><el-button type="primary" :disabled="!preparation?.trainReady" @click="creationStep = 2; rememberSelection()">继续配置</el-button></div></section>
  <section v-show="creationStep === 2" class="work-panel"><div class="work-heading"><h2>模型与训练参数</h2><RouterLink :to="{path:'/models',query:{dataset:datasetId,version:versionId}}" class="link-button">模型管理与预测</RouterLink></div><p v-if="parentModel" class="parent-model-summary">起始模型：<strong>{{parentModel.name}} · v{{parentModel.versionNumber||1}}</strong> · {{neural?'继承该版本权重':'重新拟合并保存新版本'}}</p><div class="bundle-families"><el-tag v-for="family in api.sixFamilies" :key="family">{{ api.modelNames[family] }}</el-tag></div>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="实验名称"><el-input v-model="name" maxlength="80" /></el-form-item><el-form-item v-if="neural" :label="parentModel?'追加训练轮数':'训练轮数'"><el-input-number v-model="config.epochs" :min="1" :max="30" :precision="0" /></el-form-item><el-form-item v-if="neural" label="神经模型设备"><el-select v-model="config.device"><el-option label="GPU / CUDA" value="cuda" /><el-option label="CPU" value="cpu" /></el-select></el-form-item><el-form-item v-if="neural" label="批大小 Batch size"><el-input-number v-model="config.batch_size" :min="1" :max="256" :precision="0" /></el-form-item><el-form-item v-if="selectedModels.some(f => ['cnn','bilstm'].includes(f))" label="CNN / BiLSTM 学习率"><el-input-number v-model="config.learning_rate" :min="0.0000001" :max="0.1" :step="0.0001" :precision="7" /></el-form-item><el-form-item v-if="selectedModels.includes('bert')" label="BERT 学习率"><el-input-number v-model="config.bert_learning_rate" :min="0.0000001" :max="0.1" :step="0.00001" :precision="7" /></el-form-item></div>
      <details><summary>高级参数</summary><div class="work-grid"><el-form-item v-for="field in [{key:'C',label:'LR / SVM 正则化 C',min:.0001,max:10000},{key:'max_iter',label:'LR / SVM 最大迭代',min:10,max:20000},{key:'n_estimators',label:'RF 树数量',min:10,max:1000},{key:'max_depth',label:'RF 最大深度',min:1,max:100},{key:'min_samples_leaf',label:'RF 最小叶节点样本',min:1,max:100},{key:'width',label:'CNN / BiLSTM 隐藏宽度',min:16,max:256},{key:'dropout',label:'Dropout',min:0,max:.8},{key:'max_length',label:'最大输入长度',min:8,max:512},{key:'patience',label:'早停耐心（0关闭）',min:0,max:30},{key:'weight_decay',label:'权重衰减',min:0,max:1},{key:'gradient_accumulation',label:'梯度累积步数',min:1,max:32}].filter(field => parameterVisible(field.key))" :key="field.key" :label="field.label"><el-input-number v-model="(config as any)[field.key]" :min="field.min" :max="field.max" :step="field.key === 'dropout' || field.key === 'weight_decay' ? .01 : 1" /></el-form-item><el-form-item v-if="classical" label="传统模型类别权重"><el-select v-model="config.class_weight"><el-option value="none" label="不调整" /><el-option value="balanced" label="平衡类别" /></el-select></el-form-item></div></details>
    </el-form><el-radio-group v-if="!parentModel" v-model="executionMode"><el-radio-button value="guided">使用已准备样本训练</el-radio-button><el-radio-button value="automatic">自动衔接准备与训练</el-radio-button></el-radio-group><p v-if="!preparation?.trainReady && executionMode === 'guided'" class="help-line">尚无可训练样本，请返回“准备样本”，或选择自动衔接。</p><div v-show="executionMode === 'guided'" class="work-actions"><el-button type="primary" :loading="busy" :disabled="!preparation?.trainReady || !selectedModels.length" @click="train">{{parentModel?(neural?'继续训练并生成新版本':'重新训练并生成新版本'):'开始六模型组训练'}}</el-button><span class="muted">六种模型共用样本划分，依次完成训练与独立评价。</span></div>
  </section>

</el-tab-pane><el-tab-pane label="训练任务与结果" name="tasks"><div class="page-toolbar"><p class="muted">打开一条任务查看进度、曲线、参数与日志。</p><div class="work-actions"><RouterLink v-if="!route.query.flow && current?.action === 'TRAIN' && current.status === 'COMPLETED'" class="link-button" :to="{path:'/models',query:{dataset:current.datasetId,version:current.inputVersionId,model:current.runId,tab:'evaluation'}}">查看本版本模型评价</RouterLink><el-button v-if="current&&!route.query.flow&&current.action!=='TRAIN'" @click="continueSetup">使用本批样本配置训练</el-button></div></div>
  <details v-if="current" class="task-configuration"><summary>本任务配置</summary><pre class="work-params">{{ JSON.stringify(current.options, null, 2) }}</pre></details>
  <div v-if="workflowContext.bundle?.pipelineId===focusBundleId" class="work-panel work-stats"><div><span>本组训练</span><strong>{{workflowContext.bundle.trainedCount}} / 6</strong></div><div><span>独立评价</span><strong>{{workflowContext.bundle.evaluatedCount}} / 6</strong></div><div><span>当前模型</span><strong>{{current?.options.family?.toUpperCase()||'准备中'}}</strong></div></div>
  <TrainingProgress v-if="current" :run="current" :events="events" @cancel="perform(cancel)" />

  <NewsSampleReport v-if="current?.action === 'GENERATE' && current.status === 'COMPLETED'" :run="current" />
  <details class="work-panel" :open="!current"><summary>运行记录 · {{ runTotal }}条</summary><div class="work-heading"><h2>运行记录</h2><el-button @click="perform(loadHistory)">刷新</el-button></div><el-table :data="history"><el-table-column prop="datasetName" label="数据集" min-width="140" /><el-table-column label="任务"><template #default="{row}">{{ api.actionNames[row.action] }} {{ api.modelNames[row.options.family] || '' }}</template></el-table-column><el-table-column label="状态"><template #default="{row}">{{ api.stateNames[row.status] }}</template></el-table-column><el-table-column label="操作" min-width="150"><template #default="{row}"><el-button size="small" @click="perform(() => viewRun(row.runId))">查看</el-button><el-button v-if="row.action === 'TRAIN'" size="small" @click="perform(() => copyRun(row))">复制参数</el-button><el-button v-if="row.action === 'GENERATE' && ['CANCELLED','INTERRUPTED','FAILED'].includes(row.status)" size="small" @click="generateSamples(row)">继续样本准备</el-button></template></el-table-column></el-table><RecordPagination v-model:current-page="runPage" v-model:page-size="runSize" :total="runTotal" @change="perform(loadHistory)" /></details>
</el-tab-pane><el-tab-pane label="校级模型与评价进度" name="school"><FormalTrainingProgress v-if="activeTab === 'school'" /></el-tab-pane></el-tabs>
  <AutomaticPipeline v-show="activeTab === 'tasks' || (activeTab === 'new' && creationStep === 2 && executionMode === 'automatic')" :setup-visible="activeTab === 'new'" :focus-id="focusBundleId" :preparation-id="preparationId" :parent-pipeline-id="parentBundleId" :dataset="detail" :version-id="versionId" :models="pipelineModels" :preparation="pipelinePreparation" :generation="{ ...generationConfig, seed: partition.seed }" :name="name" @created="id=>focusBundleId=id" @view="followRun" @open="id => { activeTab = 'tasks'; void perform(() => viewRun(id)) }" />
</template>

<style scoped>.bundle-families{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}.creation-steps{display:flex;gap:0;margin-bottom:22px;border:1px solid var(--line);background:var(--canvas)}.creation-steps button{display:flex;align-items:center;justify-content:flex-start;gap:12px;flex:1;padding:16px 18px;border:0;border-right:1px solid var(--line);background:none;color:var(--muted);cursor:pointer;font-size:13px}.creation-steps button:last-child{border-right:0}.creation-steps button.selected{color:var(--el-color-primary);background:var(--soft);font-weight:600}.creation-steps button>span{width:25px;height:25px;display:grid;place-items:center;border:1px solid var(--line);font-size:12px}.creation-steps button>.app-icon{margin-left:auto}.task-configuration{margin-bottom:18px}@media(max-width:650px){.creation-steps button{padding:12px 8px;gap:6px;font-size:11px}.creation-steps button>.app-icon{display:none}}</style>
