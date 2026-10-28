<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import * as api from '../api/training'
import * as datasets from '../api/workbench'
import type { ComputeRun, ComputeEvent, Model } from '../api/training'
import type { Detail, Dataset } from '../api/workbench'
import TrainingProgress from '../components/workbench/TrainingProgress.vue'
import EvaluationCharts from '../components/workbench/EvaluationCharts.vue'
import ModelComparison from '../components/workbench/ModelComparison.vue'
import PredictionResults from '../components/workbench/PredictionResults.vue'
import '../styles/workbench.css'
const items = ref<Model[]>([]), selected = ref<Model | null>(null), page = ref(1), total = ref(0), q = ref(''), archived = ref(false), busy = ref(false), error = ref('')
const sentence1 = ref(''), sentence2 = ref(''), current = ref<ComputeRun | null>(null), events = ref<ComputeEvent[]>([]), selectedRun = ref('')
const predictionFile = ref<File | null>(null)
const dataItems = ref<Dataset[]>([]), datasetId = ref(''), versionId = ref(''), preparationId = ref(''), detail = ref<Detail | null>(null), dataQuery = ref(''), dataPage = ref(1), dataTotal = ref(0)
const past = ref<ComputeRun[]>([]), resultTab = ref('predict'), runPage = ref(1), runTotal = ref(0), compared = ref<Model[]>([])
let timer: ReturnType<typeof setInterval> | undefined, alive = true, ticket = 0
const preparations = computed(() => (detail.value?.runs as ComputeRun[] ?? []).filter(r => ['PREPARE', 'GENERATE'].includes(r.action) && r.status === 'COMPLETED' && r.inputVersionId === versionId.value && r.result?.trainReady))
const cleanVersions = computed(() => detail.value?.versions.filter(v => v.stage === 'CLEAN' && v.status === 'READY') ?? [])
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task() } catch (value) { error.value = value instanceof Error ? value.message : '操作失败，请重试' } finally { busy.value = false } }
async function load() { const result = await api.models(page.value, q.value, archived.value); items.value = result.items; total.value = result.total; compared.value = compared.value.map(model => result.items.find(item => item.modelId === model.modelId) ?? model) }
async function loadModelHistory() { const id = selected.value?.modelId, requestedPage = runPage.value; if (!id) return; const result = await api.runs(requestedPage, '', id); if (alive && selected.value?.modelId === id && runPage.value === requestedPage) { past.value = result.items; runTotal.value = result.total } }
function toggleCompare(model: Model, checked: boolean) { if (!checked) { compared.value = compared.value.filter(item => item.modelId !== model.modelId); return } if (compared.value.some(item => item.modelId === model.modelId)) return; if (compared.value.length === 6) { error.value = '最多同时比较6个模型'; return } compared.value = [...compared.value, model] }
async function loadData() { const data = await datasets.datasets(dataPage.value, dataQuery.value, false); dataItems.value = data.items; dataTotal.value = data.total }
async function chooseData() { detail.value = await datasets.dataset(datasetId.value); versionId.value = cleanVersions.value[0]?.versionId ?? ''; preparationId.value = preparations.value[0]?.runId ?? '' }
function chooseVersion() { preparationId.value = preparations.value[0]?.runId ?? '' }
function stop() { if (timer) clearInterval(timer); timer = undefined }
async function choose(model: Model) { ticket++; stop(); selected.value = model; current.value = null; events.value = []; predictionFile.value = null; past.value = []; runPage.value = 1; runTotal.value = 0; datasetId.value = model.datasetId; await Promise.all([chooseData(), loadModelHistory()]) }
async function observe(id: string) {
  stop(); selectedRun.value = id; current.value = null; const token = ++ticket; let refreshing = false
  const refresh = async () => {
    if (refreshing || !alive || token !== ticket) return; refreshing = true
    try {
      const run = await api.run(id); let incoming = await api.events(id, events.value.at(-1)?.sequence ?? 0)
      if (!alive || token !== ticket) return; current.value = run
      do { const known = new Set(events.value.map(e => e.sequence)); events.value = [...events.value, ...incoming.filter(e => !known.has(e.sequence))].slice(-1000); if (incoming.length < 500) break; incoming = await api.events(id, events.value.at(-1)?.sequence ?? 0) } while (alive && token === ticket)
      if (!alive || token !== ticket) return
      if (api.terminal(run.status)) { stop(); await Promise.all([load(), loadModelHistory()]) }
    } catch (value) { if (alive && token === ticket) error.value = value instanceof Error ? value.message : '读取任务失败' } finally { refreshing = false }
  }
  events.value = []; await refresh(); const observed = current.value as ComputeRun | null; if (alive && token === ticket && observed && !api.terminal(observed.status)) timer = setInterval(() => void refresh(), 2000)
}
async function predict(batch = false) { await perform(async () => {
  if (!selected.value || !versionId.value) throw new Error('请选择模型和清洗版本')
  if (!batch && (!sentence1.value.trim() || !sentence2.value.trim())) throw new Error('请填写两段待比对文本')
  const body: Record<string, unknown> = { datasetId: datasetId.value, versionId: versionId.value, action: 'PREDICT', modelId: selected.value.modelId, name: `${selected.value.name} · 预测` }
  if (!batch) body.rows = [{ sentence1: sentence1.value, sentence2: sentence2.value }]
  else if (preparationId.value) body.preparationId = preparationId.value
  const result = await api.start(body); resultTab.value = 'predict'; await observe(result.runId)
}) }
async function evaluate() { await perform(async () => {
  if (!selected.value || !preparationId.value) throw new Error('请选择带有测试集的样本划分')
  const result = await api.start({ datasetId: datasetId.value, versionId: versionId.value, action: 'EVALUATE', preparationId: preparationId.value, modelId: selected.value.modelId, name: `${selected.value.name} · 测试集评价` })
  resultTab.value = 'evaluation'; await observe(result.runId)
}) }
function choosePredictionFile(event: Event) { predictionFile.value = (event.target as HTMLInputElement).files?.[0] ?? null }
async function uploadPredict() { await perform(async () => {
  if (!selected.value || !predictionFile.value) throw new Error('请选择待预测CSV或JSONL文件')
  if (!/\.(csv|jsonl)$/i.test(predictionFile.value.name) || !predictionFile.value.size || predictionFile.value.size > 50 * 1024 ** 2) throw new Error('请选择不超过50MiB的CSV或JSONL文件')
  const result = await api.predictFile(selected.value.modelId, predictionFile.value); resultTab.value = 'predict'; await observe(result.runId)
}) }
async function rename(model: Model) { try { const result = await ElMessageBox.prompt('输入模型名称', '重命名', { inputValue: model.name, inputValidator: value => !!value?.trim() && value.length <= 120 || '请输入1—120字', confirmButtonText: '保存', cancelButtonText: '取消' }); await api.updateModel(model.modelId, { name: result.value }); await load(); if (selected.value?.modelId === model.modelId) selected.value.name = result.value } catch (value) { if (value !== 'cancel' && value !== 'close') throw value } }
async function archive(model: Model) { await api.updateModel(model.modelId, { archived: !model.archived }); if (selected.value?.modelId === model.modelId) { selected.value = null; stop(); ticket++ } await load() }
async function cancel() { if (current.value) { await datasets.cancel(current.value.runId); await observe(current.value.runId) } }
onMounted(() => void perform(async () => { await Promise.all([load(), loadData()]) }))
onBeforeUnmount(() => { alive = false; ticket++; stop() })
</script>
<template>
  <p v-if="error" class="work-error" role="alert">{{ error }}</p>
  <section class="work-panel"><div class="work-heading"><div><h2>实验模型库</h2><span class="muted">选择已训练模型，查看参数、评价或执行句对预测。</span></div><RouterLink to="/training">新建训练</RouterLink></div><div class="work-search"><el-input v-model="q" placeholder="搜索模型名称" @change="page = 1; perform(load)" /><el-checkbox v-model="archived" @change="page = 1; perform(load)">归档</el-checkbox><el-button @click="perform(load)">刷新</el-button></div>
    <el-table :data="items" highlight-current-row @current-change="(row: Model | null) => row && perform(() => choose(row))"><el-table-column label="比较" width="70"><template #default="{ row }"><span @click.stop><el-checkbox :model-value="compared.some(item => item.modelId === row.modelId)" :disabled="compared.length >= 6 && !compared.some(item => item.modelId === row.modelId)" :aria-label="`比较${row.name}`" @change="(value: unknown) => toggleCompare(row, Boolean(value))" /></span></template></el-table-column><el-table-column prop="name" label="模型" min-width="180" /><el-table-column label="算法" min-width="130"><template #default="{row}">{{ api.modelNames[row.family] }}</template></el-table-column><el-table-column label="训练样本"><template #default="{row}">{{ row.manifest.trainRows.toLocaleString() }}</template></el-table-column><el-table-column label="验证 Macro-F1"><template #default="{row}">{{ (row.manifest.validation.macro_f1 * 100).toFixed(2) }}%</template></el-table-column><el-table-column label="操作" min-width="150"><template #default="{row}"><el-button link @click.stop="perform(() => rename(row))">重命名</el-button><el-button link @click.stop="perform(() => archive(row))">{{ row.archived ? '恢复' : '归档' }}</el-button></template></el-table-column></el-table><el-pagination layout="prev, pager, next" :page-size="20" :total="total" v-model:current-page="page" @current-change="perform(load)" />
  </section>
  <ModelComparison :models="compared" @remove="id => compared = compared.filter(model => model.modelId !== id)" @clear="compared = []" />
  <template v-if="selected"><section class="work-panel"><div class="work-heading"><h2>{{ selected.name }}</h2><RouterLink :to="`/training?run=${selected.runId}`">训练记录与调参</RouterLink></div><div class="work-stats"><div><span>训练记录</span><strong>{{ selected.manifest.trainRows.toLocaleString() }}</strong></div><div><span>训练耗时</span><strong>{{ selected.manifest.elapsedSeconds.toFixed(1) }}<small> 秒</small></strong></div><div><span>最佳验证轮 / 拟合迭代</span><strong>{{ selected.manifest.bestEpoch ?? selected.manifest.iterations ?? '—' }}</strong></div></div><details><summary>模型参数与保存信息</summary><pre class="work-params">{{ JSON.stringify(selected.manifest.parameters, null, 2) }}</pre><p>重载最大差值 {{ selected.manifest.reloadMaxDifference }} · 拟合{{ selected.manifest.converged ? '完成' : '达到迭代上限' }}</p></details><EvaluationCharts :metrics="selected.manifest.validation" /></section>
    <section class="work-panel"><div class="work-heading"><h2>评估与预测数据</h2><RouterLink to="/datasets">批量导入句对</RouterLink></div><div class="work-search"><el-input v-model="dataQuery" placeholder="搜索数据集" @change="dataPage = 1; perform(loadData)" /><el-pagination small layout="prev, next" :page-size="12" :total="dataTotal" v-model:current-page="dataPage" @current-change="perform(loadData)" /></div><el-form label-position="top"><div class="work-grid"><el-form-item label="数据集"><el-select v-model="datasetId" @change="perform(chooseData)"><el-option v-for="item in dataItems" :key="item.datasetId" :value="item.datasetId" :label="item.name" /><el-option v-if="detail && !dataItems.some(d => d.datasetId === detail!.datasetId)" :value="detail.datasetId" :label="detail.name" /></el-select></el-form-item><el-form-item label="清洗版本"><el-select v-model="versionId" @change="chooseVersion"><el-option v-for="version in cleanVersions" :key="version.versionId" :value="version.versionId" :label="`${version.versionId.slice(0,8)} · ${version.rowCount}条`" /></el-select></el-form-item><el-form-item label="测试集所属划分"><el-select v-model="preparationId"><el-option v-for="run in preparations" :key="run.runId" :value="run.runId" :label="run.runId.slice(0,8)" /></el-select></el-form-item></div></el-form><div class="work-actions"><el-button :disabled="busy || !preparationId || selected.archived" @click="evaluate">在测试集评估</el-button><el-button :disabled="busy || !versionId || selected.archived || (detail?.kind !== 'PAIRS' && !preparationId)" @click="predict(true)">批量预测句对样本</el-button></div>
      <details><summary>上传文件批量预测</summary><p class="muted">CSV / JSONL：sentence1、sentence2；label可选，最多50MiB。</p><div class="work-actions"><input :key="selected.modelId" type="file" accept=".csv,.jsonl" aria-label="上传待预测句对文件" @change="choosePredictionFile" /><el-button :loading="busy" :disabled="!predictionFile || selected.archived" @click="uploadPredict">上传并预测</el-button></div></details>
      <el-tabs v-model="resultTab"><el-tab-pane label="单条预测" name="predict"><el-form label-position="top"><div class="work-grid"><el-form-item label="文本一"><el-input v-model="sentence1" type="textarea" :rows="5" maxlength="20000" /></el-form-item><el-form-item label="文本二"><el-input v-model="sentence2" type="textarea" :rows="5" maxlength="20000" /></el-form-item></div></el-form><el-button type="primary" :loading="busy" :disabled="selected.archived" @click="predict(false)">开始预测</el-button></el-tab-pane><el-tab-pane label="测试评价" name="evaluation"><p>使用所选划分的测试集计算指标，训练重合检查在执行前完成。</p></el-tab-pane></el-tabs>
    </section>
    <TrainingProgress v-if="current" :run="current" :events="events" @cancel="perform(cancel)" />
    <section v-if="current?.status === 'COMPLETED' && current.result?.metrics" class="work-panel"><EvaluationCharts :metrics="current.result.metrics" /></section>
    <PredictionResults v-if="current?.status === 'COMPLETED' && ['PREDICT', 'EVALUATE'].includes(current.action)" :key="current.runId" :run-id="current.runId" :action="current.action" :input-name="current.result?.inputName" />
    <section class="work-panel"><h2>本模型任务 · {{ runTotal }}条</h2><el-table :data="past" empty-text="暂无任务"><el-table-column label="任务"><template #default="{row}">{{ api.actionNames[row.action] }}</template></el-table-column><el-table-column label="状态"><template #default="{row}">{{ api.stateNames[row.status] }}</template></el-table-column><el-table-column label="查看"><template #default="{row}"><el-button link @click="perform(() => observe(row.runId))">打开结果</el-button></template></el-table-column></el-table><el-pagination v-model:current-page="runPage" :total="runTotal" :page-size="20" layout="total, prev, pager, next" @current-change="perform(loadModelHistory)" /></section>
  </template><el-empty v-else description="选择模型查看详情，或新建一次训练" />
</template>
