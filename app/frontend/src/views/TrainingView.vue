<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as datasets from '../api/workbench'
import * as api from '../api/training'
import type { ComputeRun, ComputeEvent, Preparation } from '../api/training'
import type { Dataset, Detail } from '../api/workbench'
import TrainingProgress from '../components/workbench/TrainingProgress.vue'
import ExperimentChart from '../components/experiments/ExperimentChart.vue'
import NewsSampleReport from '../components/workbench/NewsSampleReport.vue'
import FormalTrainingProgress from '../components/workbench/FormalTrainingProgress.vue'
import '../styles/workbench.css'
const route = useRoute(), router = useRouter(), error = ref(''), busy = ref(false), q = ref(''), dataPage = ref(1), dataTotal = ref(0), dataItems = ref<Dataset[]>([])
const datasetId = ref(''), versionId = ref(''), detail = ref<Detail | null>(null), preparationId = ref(''), current = ref<ComputeRun | null>(null), events = ref<ComputeEvent[]>([])
const runPage = ref(1), runTotal = ref(0), history = ref<ComputeRun[]>([]), selectedModels = ref(['lr'])
const partition = reactive({ train: 80, validation: 10, test: 10, seed: 20261028 }), name = ref('')
const generationConfig = reactive({ max_originals: 0, segment_characters: 360, min_characters: 64, variants: 1, negative_candidates: 40, negatives_per_positive: 1, attempts: 2, device: 'cuda', reuse_existing: true })
const config = reactive({ C: 1, max_iter: 1000, class_weight: 'none', n_estimators: 100, max_depth: 20, min_samples_leaf: 1, epochs: 3, batch_size: 32, learning_rate: .001, bert_learning_rate: .00002, width: 64, dropout: .2, max_length: 128, patience: 2, weight_decay: .01, gradient_accumulation: 1, device: 'cuda' })
let timer: ReturnType<typeof setInterval> | undefined, stream: EventSource | undefined, generation = 0, alive = true, refreshing = false
const cleanVersions = computed(() => detail.value?.versions.filter(v => v.stage === 'CLEAN' && v.status === 'READY') ?? [])
const preparations = computed(() => (detail.value?.runs as ComputeRun[] ?? []).filter(run => ['PREPARE', 'GENERATE'].includes(run.action) && run.status === 'COMPLETED' && run.inputVersionId === versionId.value))
const preparation = computed(() => preparations.value.find(r => r.runId === preparationId.value)?.result as Preparation | undefined)
const distribution = computed(() => ({ tooltip: { trigger: 'axis', borderRadius: 0 }, legend: {}, grid: { left: 45, right: 20, bottom: 35 }, xAxis: { type: 'category', data: ['训练', '验证', '测试', '校准'] }, yAxis: { type: 'value' }, series: ['0', '1'].map(label => ({ name: label === '0' ? '非复用' : '复用', type: 'bar', stack: 'labels', data: ['train', 'validation', 'test', 'calibration'].map(key => preparation.value?.partitions[key]?.labels[label] ?? 0) })) }))
function failure(value: unknown) { error.value = value instanceof Error ? value.message : '操作失败，请重试' }
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task() } catch (value) { failure(value) } finally { busy.value = false } }
async function loadData() { const result = await datasets.datasets(dataPage.value, q.value, false); dataItems.value = result.items; dataTotal.value = result.total }
async function loadHistory() { const result = await api.runs(runPage.value); history.value = result.items; runTotal.value = result.total }
async function chooseDataset() { if (!datasetId.value) return; detail.value = await datasets.dataset(datasetId.value); if (!cleanVersions.value.some(v => v.versionId === versionId.value)) versionId.value = cleanVersions.value[0]?.versionId ?? ''; chooseVersion(); name.value = `${detail.value.name.slice(0, 70)}实验` }
function chooseVersion() { preparationId.value = preparations.value[0]?.runId ?? '' }
function stop() { stream?.close(); stream = undefined; if (timer) clearInterval(timer); timer = undefined }
function consume(incoming: ComputeEvent[]) { const known = new Set(events.value.map(e => e.sequence)); events.value = [...events.value, ...incoming.filter(e => !known.has(e.sequence))].slice(-1000) }
async function viewRun(id: string) {
  stop(); const token = ++generation; current.value = await api.run(id); if (token !== generation || !alive) return
  const viewed = current.value
  if (detail.value?.datasetId !== viewed.datasetId || versionId.value !== viewed.inputVersionId) { datasetId.value = viewed.datasetId; versionId.value = viewed.inputVersionId; await chooseDataset(); if (token !== generation || !alive) return }
  if (viewed.status === 'COMPLETED' && ['PREPARE', 'GENERATE'].includes(viewed.action)) preparationId.value = viewed.runId
  else if (viewed.options.preparationId) preparationId.value = viewed.options.preparationId
  events.value = []; let batch: ComputeEvent[]; do { batch = await api.events(id, events.value.at(-1)?.sequence ?? 0); if (token !== generation || !alive) return; consume(batch) } while (batch.length === 500)
  void router.replace({ query: { ...route.query, run: id } })
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
async function train() { await perform(async () => {
  if (!preparation.value?.trainReady || !selectedModels.value.length) throw new Error('请选择可训练的样本划分和模型')
  const started: string[] = []
  for (const family of selectedModels.value) {
    const parameters = { ...config, seed: partition.seed, device: ['lr', 'svm', 'rf'].includes(family) ? 'cpu' : config.device, learning_rate: family === 'bert' ? config.bert_learning_rate : config.learning_rate } as Record<string, unknown>
    delete parameters.bert_learning_rate
    const run = await api.start({ action: 'TRAIN', datasetId: datasetId.value, versionId: versionId.value, preparationId: preparationId.value, family, name: `${name.value} · ${api.modelNames[family]}`, parameters })
    started.push(run.runId)
  }
  await loadHistory(); if (started[0]) await viewRun(started[0])
}) }
async function generateSamples(resume?: ComputeRun) { await perform(async () => {
  const source = resume?.options.preparationId ?? preparationId.value
  if (!source) throw new Error('请先选择新闻分组版本')
  const parameters = resume?.options.parameters ?? { ...generationConfig, seed: partition.seed }
  const result = await api.start({ action: 'GENERATE', datasetId: resume?.datasetId ?? datasetId.value, versionId: resume?.inputVersionId ?? versionId.value, preparationId: source, parameters, ...(resume ? { resumeRunId: resume.runId } : {}), name: '新闻原稿自动准备句对' })
  await loadHistory(); await viewRun(result.runId)
}) }
async function copyRun(run: ComputeRun) { datasetId.value = run.datasetId; versionId.value = run.inputVersionId; await chooseDataset(); preparationId.value = run.options.preparationId ?? preparationId.value; selectedModels.value = run.options.family ? [run.options.family] : ['lr']; Object.assign(config, run.options.parameters ?? {}); if (run.options.family === 'bert') config.bert_learning_rate = Number(run.options.parameters?.learning_rate ?? .00002); name.value = (run.options.name ?? name.value).slice(0, 80) + ' 调参' }
async function cancel() { if (current.value) { await datasets.cancel(current.value.runId); await viewRun(current.value.runId) } }
onMounted(() => void perform(async () => { await Promise.all([loadData(), loadHistory()]); if (typeof route.query.dataset === 'string') { datasetId.value = route.query.dataset; if (typeof route.query.version === 'string') versionId.value = route.query.version; await chooseDataset() } if (typeof route.query.run === 'string') await viewRun(route.query.run) }))
onBeforeUnmount(() => { alive = false; generation++; stop() })
</script>
<template>
  <p v-if="error" role="alert" class="work-error">{{ error }}</p>
  <FormalTrainingProgress />
  <section class="work-panel"><div class="work-heading"><div><h2>选择训练数据</h2><span class="muted">选定清洗版本，先准备样本，再配置模型。</span></div><RouterLink to="/datasets">上传与清洗数据</RouterLink></div>
    <div class="work-search"><el-input v-model="q" placeholder="搜索数据集" aria-label="搜索训练数据集" @change="dataPage = 1; perform(loadData)" /><el-button @click="perform(loadData)">搜索</el-button><el-pagination small layout="prev, next" :page-size="12" :total="dataTotal" v-model:current-page="dataPage" @current-change="perform(loadData)" /></div>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="数据集"><el-select v-model="datasetId" aria-label="训练数据集" @change="perform(chooseDataset)"><el-option v-for="item in dataItems" :key="item.datasetId" :label="`${item.name} · ${item.kind === 'NEWS' ? '新闻' : '句对'}`" :value="item.datasetId" /><el-option v-if="detail && !dataItems.some(d => d.datasetId === detail!.datasetId)" :label="detail.name" :value="detail.datasetId" /></el-select></el-form-item><el-form-item label="清洗版本"><el-select v-model="versionId" aria-label="训练清洗版本" @change="chooseVersion"><el-option v-for="version in cleanVersions" :key="version.versionId" :label="`${version.versionId.slice(0, 8)} · ${version.rowCount?.toLocaleString()}条`" :value="version.versionId" /></el-select></el-form-item><el-form-item label="随机种子"><el-input-number v-model="partition.seed" :min="0" :max="2147483647" :precision="0" /></el-form-item></div>
    <details open><summary>样本分组与划分</summary><div class="work-grid"><el-form-item v-for="(label, key) in { train: '训练集 %', validation: '验证集 %', test: '测试集 %' }" :key="key" :label="label"><el-input-number v-model="partition[key]" :min="1" :max="98" :precision="0" /></el-form-item></div><p class="muted">按来源、事件及相同句子归组；已有独立分区保持隔离。</p><el-button :disabled="!versionId || busy" @click="prepare">准备样本与划分</el-button></details>
    <el-form-item label="样本版本"><el-select v-model="preparationId" aria-label="样本划分"><el-option v-for="run in preparations" :key="run.runId" :value="run.runId" :label="`${run.runId.slice(0, 8)} · ${run.result?.trainReady ? '可训练' : run.action === 'PREPARE' && detail?.kind === 'NEWS' ? '新闻分组与段落池' : '类别待补充'}`" /></el-select></el-form-item></el-form>
    <template v-if="preparation"><div class="work-stats"><div><span>原始记录</span><strong>{{ preparation.inputRows.toLocaleString() }}</strong></div><div><span>独立分组</span><strong>{{ preparation.groups.toLocaleString() }}</strong></div><div><span>{{ preparation.requiresLabels ? '待准备标签的段落' : '可训练样本' }}</span><strong>{{ (preparation.requiresLabels ? preparation.segments : preparation.outputRows ?? preparation.inputRows).toLocaleString() }}</strong></div></div>
    <el-table :data="Object.entries(preparation.partitions).map(([name, value]) => ({ name: ({train:'训练',validation:'验证',test:'测试',calibration:'校准'} as Record<string,string>)[name], ...value }))"><el-table-column prop="name" label="分区" /><el-table-column prop="rows" label="记录数" /><el-table-column prop="groups" label="组数" /><el-table-column label="类别"><template #default="{row}">{{ Object.entries(row.labels).map(([k,v]) => `${k}: ${v}`).join(' / ') }}</template></el-table-column></el-table>
    <ExperimentChart v-if="!preparation.requiresLabels" title="划分类别分布" :option="distribution as any" /><p v-if="preparation.requiresLabels">新闻分组已保存，可开始自动准备句对。</p><p v-else-if="!preparation.trainReady" class="work-error">类别不足的分区：{{ preparation.missingClassPartitions.join('、') }}</p></template>
  </section>
  <section v-if="detail?.kind === 'NEWS'" class="work-panel"><div class="work-heading"><div><h2>新闻原稿自动准备训练样本</h2><span class="muted">选择新闻分组版本，自动完成改写、检查、负例准备与样本保存。</span></div></div><el-form label-position="top"><div class="work-grid"><el-form-item label="处理原稿数（0为全部）"><el-input-number v-model="generationConfig.max_originals" :min="0" :max="100000" :precision="0" /></el-form-item><el-form-item label="每段改写数量"><el-input-number v-model="generationConfig.variants" :min="1" :max="4" :precision="0" /></el-form-item><el-form-item label="执行设备"><el-select v-model="generationConfig.device"><el-option value="cuda" label="GPU / CUDA" /><el-option value="cpu" label="CPU" /></el-select></el-form-item></div><details><summary>样本准备参数</summary><div class="work-grid"><el-form-item label="段落窗口字数"><el-input-number v-model="generationConfig.segment_characters" :min="128" :max="512" :precision="0" /></el-form-item><el-form-item label="最少有效字数"><el-input-number v-model="generationConfig.min_characters" :min="32" :max="256" :precision="0" /></el-form-item><el-form-item label="负例候选数"><el-input-number v-model="generationConfig.negative_candidates" :min="5" :max="200" :precision="0" /></el-form-item><el-form-item label="每个正例对应负例数"><el-input-number v-model="generationConfig.negatives_per_positive" :min="1" :max="4" :precision="0" /></el-form-item><el-form-item label="最多尝试次数"><el-input-number v-model="generationConfig.attempts" :min="1" :max="4" :precision="0" /></el-form-item></div><el-checkbox v-model="generationConfig.reuse_existing">复用原文与检查均匹配的已有改写</el-checkbox></details></el-form><div class="work-actions"><el-button type="primary" :loading="busy" :disabled="!preparation?.requiresLabels" @click="generateSamples()">自动准备训练样本</el-button><span class="muted">完成后，在样本版本中选择生成结果并训练模型。</span></div></section>
  <section class="work-panel"><div class="work-heading"><h2>模型与训练参数</h2><RouterLink to="/models">模型管理与预测</RouterLink></div><el-checkbox-group v-model="selectedModels"><el-checkbox v-for="(label, family) in api.modelNames" :key="family" :value="family">{{ label }}</el-checkbox></el-checkbox-group>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="实验名称"><el-input v-model="name" maxlength="80" /></el-form-item><el-form-item label="训练轮数"><el-input-number v-model="config.epochs" :min="1" :max="30" :precision="0" /></el-form-item><el-form-item label="神经模型设备"><el-select v-model="config.device"><el-option label="GPU / CUDA" value="cuda" /><el-option label="CPU" value="cpu" /></el-select></el-form-item><el-form-item label="Batch size"><el-input-number v-model="config.batch_size" :min="1" :max="256" :precision="0" /></el-form-item><el-form-item label="CNN / BiLSTM 学习率"><el-input-number v-model="config.learning_rate" :min="0.0000001" :max="0.1" :step="0.0001" :precision="7" /></el-form-item><el-form-item label="BERT 学习率"><el-input-number v-model="config.bert_learning_rate" :min="0.0000001" :max="0.1" :step="0.00001" :precision="7" /></el-form-item></div>
      <details><summary>高级参数</summary><div class="work-grid"><el-form-item v-for="field in [{key:'C',label:'LR / SVM 正则化 C',min:.0001,max:10000},{key:'max_iter',label:'LR / SVM 最大迭代',min:10,max:20000},{key:'n_estimators',label:'RF 树数量',min:10,max:1000},{key:'max_depth',label:'RF 最大深度',min:1,max:100},{key:'min_samples_leaf',label:'RF 最小叶节点样本',min:1,max:100},{key:'width',label:'CNN / BiLSTM 隐藏宽度',min:16,max:256},{key:'dropout',label:'Dropout',min:0,max:.8},{key:'max_length',label:'最大输入长度',min:8,max:512},{key:'patience',label:'早停耐心（0关闭）',min:0,max:30},{key:'weight_decay',label:'权重衰减',min:0,max:1},{key:'gradient_accumulation',label:'梯度累积步数',min:1,max:32}]" :key="field.key" :label="field.label"><el-input-number v-model="(config as any)[field.key]" :min="field.min" :max="field.max" :step="field.key === 'dropout' || field.key === 'weight_decay' ? .01 : 1" /></el-form-item><el-form-item label="传统模型类别权重"><el-select v-model="config.class_weight"><el-option value="none" label="不调整" /><el-option value="balanced" label="平衡类别" /></el-select></el-form-item></div></details>
    </el-form><div class="work-actions"><el-button type="primary" :loading="busy" :disabled="!preparation?.trainReady" @click="train">开始训练所选模型</el-button><span class="muted">多模型依次排队，验证集用于选择最佳轮次。</span></div>
  </section>
  <TrainingProgress v-if="current" :run="current" :events="events" @cancel="perform(cancel)" />
  <NewsSampleReport v-if="current?.action === 'GENERATE' && current.status === 'COMPLETED'" :run="current" />
  <section class="work-panel"><div class="work-heading"><h2>运行记录</h2><el-button @click="perform(loadHistory)">刷新</el-button></div><el-table :data="history"><el-table-column prop="datasetName" label="数据集" min-width="140" /><el-table-column label="任务"><template #default="{row}">{{ api.actionNames[row.action] }} {{ api.modelNames[row.options.family] || '' }}</template></el-table-column><el-table-column label="状态"><template #default="{row}">{{ api.stateNames[row.status] }}</template></el-table-column><el-table-column label="操作" min-width="150"><template #default="{row}"><el-button link @click="perform(() => viewRun(row.runId))">查看</el-button><el-button v-if="row.action === 'TRAIN'" link @click="perform(() => copyRun(row))">复制参数</el-button><el-button v-if="row.action === 'GENERATE' && ['CANCELLED','INTERRUPTED','FAILED'].includes(row.status)" link @click="generateSamples(row)">继续样本准备</el-button></template></el-table-column></el-table><el-pagination layout="prev, pager, next" v-model:current-page="runPage" :total="runTotal" :page-size="20" @current-change="perform(loadHistory)" /></section>
</template>
