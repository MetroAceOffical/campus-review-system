<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import * as api from '../api/workbench'
import type { Audit, Cleaning, Dataset, Detail, Progress, Run } from '../api/workbench'
import DatasetCharts from '../components/workbench/DatasetCharts.vue'
const route = useRoute(), router = useRouter()

const organizations = ref<Array<{ organizationId: string; name: string }>>([]), items = ref<Dataset[]>([])
const detail = ref<Detail | null>(null), currentRun = ref<Run | null>(null), audit = ref<Audit | null>(null), cleaning = ref<Cleaning | null>(null)
const error = ref(''), busy = ref(false), loading = ref(false), q = ref(''), archived = ref(false), page = ref(1), total = ref(0)
const form = reactive({ name: '', kind: 'NEWS', organizationId: '' }), file = ref<File | null>(null)
const inputVersion = ref(''), mapping = reactive<Record<string, string>>({}), events = ref<Progress[]>([]), columns = ref<string[]>([])
const options = reactive({ strip_html: true, normalize_whitespace: true, remove_duplicates: true, min_text_length: 1, max_text_length: 1000000 })
const samplePage = ref(1), sampleTotal = ref(0), samples = ref<Array<Record<string, unknown>>>([])
let stream: EventSource | undefined, timer: ReturnType<typeof setInterval> | undefined, generation = 0, versionGeneration = 0, alive = true
const terminal = (status: string) => ['COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'].includes(status)
const statusName: Record<string, string> = { QUEUED: '排队中', RUNNING: '处理中', COMPLETED: '处理完成', FAILED: '处理失败', CANCELLED: '已取消', INTERRUPTED: '已中断', PARSED: '已解析', CLEANING: '清洗中', SAVING: '保存版本' }
const fieldName: Record<string, string> = { text: '正文', title: '标题', id: '编号', source_institution: '来源学校', url: '来源网址', published_at: '发布日期', department: '材料部门', sentence1: '原句', sentence2: '改写句', label: '标签', source_id: '原作编号', group_id: '分组编号', label_origin: '标签来源' }
const fields = computed(() => detail.value?.kind === 'PAIRS' ? ['sentence1', 'sentence2', 'label', 'source_id', 'group_id', 'label_origin'] : ['text', 'title', 'id', 'source_institution', 'url', 'published_at', 'department'])
const active = computed(() => currentRun.value && !terminal(currentRun.value.status))
const selectedVersion = computed(() => detail.value?.versions.find(v => v.versionId === inputVersion.value))
const cleanVersion = computed(() => selectedVersion.value?.stage === 'CLEAN' && selectedVersion.value.status === 'READY' ? selectedVersion.value : undefined)
const latestProgress = computed(() => [...events.value].reverse().find(e => e.data.stage === 'CLEANING' && typeof e.data.total === 'number'))
const percent = computed(() => { const value = latestProgress.value?.data; return value?.total ? Math.min(100, Math.round((value.processed ?? 0) / value.total * 100)) : 0 })
function stop() { stream?.close(); stream = undefined; if (timer) clearInterval(timer); timer = undefined }
function message(value: unknown) { error.value = value instanceof Error ? value.message : '操作未完成，请重试' }
async function refreshList() { const result = await api.datasets(page.value, q.value, archived.value); if (!alive) return; items.value = result.items; total.value = result.total }
async function initialize() {
  loading.value = true; error.value = ''
  try { const [departments] = await Promise.all([api.organizations(), refreshList()]); if (!alive) return; organizations.value = departments; form.organizationId ||= departments[0]?.organizationId ?? ''; if (!detail.value && typeof route.query.dataset === 'string') await select(route.query.dataset, typeof route.query.version === 'string' ? route.query.version : undefined) }
  catch (value) { message(value) } finally { loading.value = false }
}
async function readSamples() {
  if (!detail.value || !cleanVersion.value) return
  const id = detail.value.datasetId, version = cleanVersion.value.versionId, token = generation, requestedPage = samplePage.value, result = await api.rows(id, version, requestedPage)
  if (alive && token === generation && detail.value?.datasetId === id && cleanVersion.value?.versionId === version && samplePage.value === requestedPage) { samples.value = result.items; sampleTotal.value = result.total }
}
async function changeVersion() {
  if (!detail.value || !inputVersion.value) return
  const ticket = ++versionGeneration, token = generation, id = detail.value.datasetId, version = inputVersion.value
  audit.value = null; cleaning.value = null; samples.value = []; samplePage.value = 1; sampleTotal.value = 0; columns.value = []
  for (const key of Object.keys(mapping)) delete mapping[key]
  void router.replace({ query: { ...route.query, dataset: id, version } })
  const valid = () => alive && ticket === versionGeneration && token === generation && detail.value?.datasetId === id && inputVersion.value === version
  try {
    if (selectedVersion.value?.stage === 'CLEAN') {
      const report = await api.report(id, version); if (!valid()) return
      cleaning.value = report; audit.value = report.after; columns.value = Object.keys(report.after.missing)
      await readSamples()
    } else {
      const matching = detail.value.runs.filter(run => run.action === 'AUDIT' && run.inputVersionId === version)
      const quality = matching.find(run => run.status === 'COMPLETED' && run.result?.audit)
      const schema = matching.find(run => run.result?.columns)
      audit.value = quality?.result?.audit ?? null; samples.value = quality?.result?.preview ?? []
      columns.value = schema?.result?.columns ?? []
      Object.assign(mapping, schema?.result?.mapping ?? schema?.mapping ?? {})
    }
  } catch (value) { if (valid()) message(value) }
}
async function select(id: string, preferredVersion?: string) {
  stop(); const token = ++generation; loading.value = true; error.value = ''
  try {
    const result = await api.dataset(id); if (!alive || token !== generation) return
    detail.value = result; currentRun.value = result.runs.find(run => ['AUDIT', 'CLEAN'].includes(run.action)) ?? null
    const candidates = [preferredVersion, currentRun.value?.status === 'COMPLETED' ? currentRun.value?.outputVersionId : undefined, currentRun.value?.inputVersionId]
    inputVersion.value = candidates.find(id => result.versions.some(version => version.versionId === id && version.status === 'READY')) ?? result.versions.find(version => version.status === 'READY')?.versionId ?? ''
    events.value = []
    await changeVersion(); if (!alive || token !== generation) return
    if (currentRun.value) {
      const runId = currentRun.value.runId, stored = await api.events(runId)
      if (!alive || token !== generation) return
      events.value = stored
      if (!terminal(currentRun.value.status)) observe(runId, token)
    }
  } catch (value) { if (token === generation) message(value) } finally { if (token === generation) loading.value = false }
}
function observe(id: string, token: number) {
  const consume = (incoming: Progress[]) => { const known = new Set(events.value.map(e => e.sequence)); events.value = [...events.value, ...incoming.filter(e => !known.has(e.sequence))].slice(-500) }
  const refresh = async () => {
    try { const run = await api.run(id); if (!alive || token !== generation) return; const incoming = await api.events(id, events.value.at(-1)?.sequence ?? 0); if (!alive || token !== generation) return; currentRun.value = run; consume(incoming); if (terminal(run.status)) { stop(); await select(run.datasetId); await refreshList() } }
    catch (value) { if (alive && token === generation) message(value) }
  }
  const fallback = () => { if (!alive || token !== generation) return; stream?.close(); stream = undefined; timer ??= setInterval(() => void refresh(), 2500) }
  if (typeof EventSource === 'undefined') { fallback(); return }
  stream = new EventSource(`/api/workbench/runs/${id}/stream?after=${events.value.at(-1)?.sequence ?? 0}`)
  stream.addEventListener('progress', event => { if (token === generation && alive) { const value = event as MessageEvent; consume([{ sequence: Number(value.lastEventId), data: JSON.parse(value.data) }]) } })
  stream.addEventListener('snapshot', event => { if (token === generation && alive && terminal(JSON.parse((event as MessageEvent).data).status)) void refresh() })
  stream.onerror = fallback
}
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task() } catch (value) { message(value) } finally { busy.value = false } }
function chooseFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] ?? null; if (file.value && !form.name) form.name = file.value.name.replace(/\.(csv|jsonl)$/i, '') }
async function upload() { await perform(async () => {
  if (!file.value || !form.name.trim() || !form.organizationId) throw new Error('请填写名称、选择部门和数据文件')
  if (file.value.size > 50 * 1024 * 1024) throw new Error('数据文件不能超过50MiB')
  const data = new FormData(); data.set('file', file.value); data.set('name', form.name); data.set('kind', form.kind); data.set('organizationId', form.organizationId)
  const result = await api.upload(data); await refreshList(); await select(result.datasetId); ElMessage.success('已上传，开始质量评估')
}) }
async function start(action: 'AUDIT' | 'CLEAN') { await perform(async () => {
  if (!detail.value || !inputVersion.value) return
  await api.start(detail.value.datasetId, inputVersion.value, action, Object.fromEntries(Object.entries(mapping).filter(([, value]) => value)), action === 'CLEAN' ? options : {})
  await select(detail.value.datasetId)
}) }
async function editName() { if (!detail.value) return; try { const result = await ElMessageBox.prompt('输入数据集名称', '重命名', { inputValue: detail.value.name, inputPattern: /^.{1,120}$/, inputErrorMessage: '请输入1—120字' }); await perform(async () => { await api.update(detail.value!.datasetId, { name: result.value }); await select(detail.value!.datasetId); await refreshList() }) } catch { /* cancelled */ } }
async function archive() { if (!detail.value) return; await perform(async () => { await api.update(detail.value!.datasetId, { archived: !detail.value!.archived }); await select(detail.value!.datasetId); await refreshList() }) }
async function cancelCurrent() { if (!currentRun.value || !detail.value) return; const id = detail.value.datasetId, runId = currentRun.value.runId; await perform(async () => { await api.cancel(runId); await select(id) }) }
function download(name: string, text: string, mime: string) { const url = URL.createObjectURL(new Blob([text], { type: mime })), link = document.createElement('a'); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url) }
function template() { download(`${form.kind.toLowerCase()}-template.csv`, '\uFEFF' + (form.kind === 'NEWS' ? 'id,title,text,department,url,published_at,source_institution\n' : 'sentence1,sentence2,label,source_id,group_id,label_origin\n'), 'text/csv;charset=utf-8') }
onMounted(initialize); onBeforeUnmount(() => { alive = false; generation++; stop() })
</script>

<template><RouterLink v-if="detail && cleanVersion && detail.kind === 'NEWS'" :to="`/reference-imports?dataset=${detail.datasetId}&version=${cleanVersion.versionId}`">批量参考入库 →</RouterLink>
  <section class="dataset-upload">
    <span class="dataset-eyebrow">DATA WORKSPACE</span><h2>批量导入，逐步处理</h2><p class="muted">选择CSV或JSONL，上传后自动评估数据质量。</p>
    <el-form label-position="top" class="upload-form" @submit.prevent="upload">
      <el-form-item label="数据集名称"><el-input v-model="form.name" maxlength="120" placeholder="例如：新闻中心历年文稿" /></el-form-item>
      <el-form-item label="所属部门"><el-select v-model="form.organizationId"><el-option v-for="org in organizations" :key="org.organizationId" :label="org.name" :value="org.organizationId" /></el-select></el-form-item>
      <el-form-item label="数据类型"><el-select v-model="form.kind"><el-option label="原始新闻" value="NEWS" /><el-option label="标签句对" value="PAIRS" /></el-select></el-form-item>
      <el-form-item label="数据文件 · 最大50MiB"><input aria-label="选择数据文件" type="file" accept=".csv,.jsonl" @change="chooseFile" /></el-form-item>
      <div class="upload-actions"><el-button type="primary" native-type="submit" :loading="busy">上传并评估</el-button><el-button @click="template">下载模板</el-button></div>
    </el-form>
  </section>
  <div v-if="error" class="dataset-error" role="alert"><el-alert :title="error" type="error" :closable="false" /><el-button @click="initialize">重试</el-button></div>
  <div class="dataset-layout" v-loading="loading">
    <section class="dataset-list">
      <div class="section-heading"><h2>我的数据集</h2><el-checkbox v-model="archived" @change="page = 1; initialize()">归档</el-checkbox></div>
      <el-input v-model="q" placeholder="搜索名称" clearable aria-label="搜索数据集" @change="page = 1; initialize()" />
      <button v-for="item in items" :key="item.datasetId" class="dataset-choice" :class="{ selected: detail?.datasetId === item.datasetId }" @click="select(item.datasetId)"><strong>{{ item.name }}</strong><span>{{ item.kind === 'NEWS' ? '原始新闻' : '标签句对' }}</span></button>
      <el-empty v-if="!items.length" description="上传一批数据开始处理" :image-size="70" />
      <el-pagination small layout="prev, pager, next" :page-size="12" :total="total" v-model:current-page="page" @current-change="initialize" />
    </section>
    <section v-if="detail" class="dataset-detail">
      <div class="section-heading"><div><h2>{{ detail.name }}</h2><span class="muted">{{ detail.kind === 'NEWS' ? '原始新闻' : '标签句对' }} · {{ detail.versions.length }}个版本</span></div><div><RouterLink v-if="cleanVersion" :to="`/training?dataset=${detail.datasetId}&version=${cleanVersion.versionId}`">准备与训练</RouterLink><el-button @click="editName">重命名</el-button><el-button :disabled="!!active" @click="archive">{{ detail.archived ? '恢复' : '归档' }}</el-button></div></div>
      <div class="version-selector"><label for="dataset-version">查看与处理版本</label><select id="dataset-version" v-model="inputVersion" aria-label="输入版本" @change="changeVersion"><option v-for="version in detail.versions.filter(v => v.status === 'READY')" :key="version.versionId" :value="version.versionId">{{ version.stage === 'RAW' ? '原始文件' : '清洗版本' }} · {{ version.versionId.slice(0, 8) }}</option></select></div>
      <div v-if="audit" class="dataset-stats"><div><span>总记录</span><el-statistic :value="audit.totalRows" /></div><div class="positive"><span>结构有效</span><el-statistic :value="audit.validRows" /></div><div class="attention"><span>待处理记录</span><el-statistic :value="audit.invalidRows" /></div><div><span>精确重复</span><el-statistic :value="audit.duplicateRows" /></div></div>
      <div v-if="currentRun" class="run-status" aria-live="polite"><div class="section-heading"><strong>{{ currentRun.action === 'AUDIT' ? '数据质量评估' : '数据清洗' }}</strong><el-tag :type="currentRun.status === 'FAILED' ? 'danger' : currentRun.status === 'COMPLETED' ? 'success' : 'info'">{{ statusName[currentRun.status] ?? currentRun.status }}</el-tag></div><el-progress v-if="latestProgress" :percentage="percent" /><p v-if="currentRun.error" class="error-text">{{ currentRun.error }}</p><el-button v-if="active" @click="cancelCurrent">取消任务</el-button></div>
      <el-tabs>
        <el-tab-pane label="质量与清洗"><DatasetCharts v-if="audit" :audit="audit" :cleaning="cleaning" :events="events" /><el-empty v-else description="等待质量评估结果" /><div v-if="cleaning" class="clean-summary"><strong>清洗保留 {{ cleaning.outputRows.toLocaleString() }} 条</strong><span>重复合并 {{ cleaning.duplicateRows }} 条</span><span>隔离 {{ cleaning.inputRows - cleaning.outputRows - cleaning.duplicateRows }} 条</span></div></el-tab-pane>
        <el-tab-pane label="字段与规则"><el-form label-position="top"><div class="mapping-grid"><el-form-item v-for="field in fields" :key="field" :label="fieldName[field]"><el-select v-model="mapping[field]" clearable placeholder="自动识别"><el-option v-for="column in columns" :key="column" :label="column" :value="column" /></el-select></el-form-item></div><el-checkbox v-model="options.strip_html">提取HTML正文</el-checkbox><el-checkbox v-model="options.normalize_whitespace">规范空白</el-checkbox><el-checkbox v-model="options.remove_duplicates">合并精确重复</el-checkbox><div class="length-options"><label>最小正文长度 <el-input-number v-model="options.min_text_length" :min="1" :max="1000000" /></label><label>最大正文长度 <el-input-number v-model="options.max_text_length" :min="options.min_text_length" :max="1000000" /></label></div></el-form></el-tab-pane>
        <el-tab-pane label="样本预览"><el-table :data="samples" max-height="420"><el-table-column v-if="detail.kind === 'NEWS'" prop="title" label="标题" min-width="110" /><el-table-column :prop="detail.kind === 'NEWS' ? 'text' : 'sentence1'" :label="detail.kind === 'NEWS' ? '正文' : '原句'" min-width="220" show-overflow-tooltip /><el-table-column v-if="detail.kind === 'PAIRS'" prop="sentence2" label="改写句" min-width="180" show-overflow-tooltip /><el-table-column v-if="detail.kind === 'NEWS'" prop="source_institution" label="来源学校" width="110" /><el-table-column v-else prop="label" label="标签" width="70" /></el-table><el-pagination v-if="cleanVersion" v-model:current-page="samplePage" :page-size="10" :total="sampleTotal" layout="total, prev, pager, next" @current-change="readSamples" /></el-tab-pane>
        <el-tab-pane label="任务与版本"><el-table :data="detail.runs"><el-table-column label="任务"><template #default="{ row }">{{ row.action === 'AUDIT' ? '质量评估' : '清洗' }}</template></el-table-column><el-table-column label="状态"><template #default="{ row }">{{ statusName[row.status] ?? row.status }}</template></el-table-column><el-table-column prop="createdAt" label="创建时间" min-width="170" /></el-table><ol class="event-list"><li v-for="event in events" :key="event.sequence">{{ statusName[event.data.stage] ?? event.data.stage }}<span v-if="event.data.total !== undefined"> · {{ event.data.processed }}/{{ event.data.total }}</span></li></ol></el-tab-pane>
      </el-tabs>
      <div class="dataset-actions"><el-button :disabled="!!active || detail.archived" :loading="busy" @click="start('AUDIT')">重新评估</el-button><el-button type="primary" :disabled="!!active || detail.archived" :loading="busy" @click="start('CLEAN')">生成清洗版本</el-button><el-button v-if="audit" @click="download('dataset-quality.json', JSON.stringify({ audit, cleaning }, null, 2), 'application/json')">导出指标</el-button><a v-if="inputVersion" :href="api.downloadUrl(detail.datasetId, inputVersion, detail.versions.find(v => v.versionId === inputVersion)?.stage === 'RAW' ? 'source' : 'corpus.jsonl')">下载输入</a><template v-if="cleanVersion"><a :href="api.downloadUrl(detail.datasetId, cleanVersion.versionId, 'corpus.jsonl')">清洗数据</a><a :href="api.downloadUrl(detail.datasetId, cleanVersion.versionId, 'quarantine.jsonl')">隔离明细</a><a :href="api.downloadUrl(detail.datasetId, cleanVersion.versionId, 'changes.jsonl')">清洗记录</a></template></div>
    </section>
    <el-empty v-else class="dataset-welcome" description="选择数据集，查看质量与处理记录" />
  </div>
</template>

<style scoped>
:deep(.el-checkbox__inner),:deep(.el-progress-bar__outer),:deep(.el-progress-bar__inner){border-radius:0}
.version-selector{display:flex;align-items:center;gap:12px;margin:14px 0;font-size:12px}.version-selector select{padding:8px;border:1px solid var(--line);border-radius:0;background:var(--canvas);color:inherit;max-width:100%}
.dataset-upload,.dataset-list,.dataset-detail{border:1px solid var(--line);background:var(--canvas);border-radius:0;padding:20px}.dataset-upload{margin-bottom:20px;background:linear-gradient(120deg,color-mix(in srgb,var(--el-color-primary) 7%,var(--canvas)),var(--canvas))}.dataset-eyebrow{font-size:11px;letter-spacing:2px;color:var(--el-color-primary)}.dataset-upload h2{font-size:23px;margin:8px 0}.dataset-upload p{font-size:13px}.upload-form{display:grid;grid-template-columns:2fr 1.2fr 1fr 2fr;gap:12px}.upload-actions{grid-column:1/-1;display:flex;gap:8px}.upload-form .el-form-item{margin-bottom:0;min-width:0}.upload-form input[type=file]{max-width:100%;font-size:12px}.dataset-layout{display:grid;grid-template-columns:270px minmax(0,1fr);gap:20px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:15px}.section-heading h2{margin:0;font-size:17px}.dataset-choice{display:grid;gap:7px;width:100%;border:1px solid var(--line);border-radius:0;background:transparent;color:inherit;text-align:left;padding:14px;margin-top:12px;cursor:pointer}.dataset-choice span{font-size:12px;color:var(--muted)}.dataset-choice.selected{border-color:var(--el-color-primary);background:color-mix(in srgb,var(--el-color-primary) 7%,transparent)}.dataset-choice:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:2px}.dataset-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}.dataset-stats>div{padding:16px;border-radius:0;background:color-mix(in srgb,var(--el-color-primary) 7%,var(--canvas))}.dataset-stats .positive{background:color-mix(in srgb,#329b8c 10%,var(--canvas))}.dataset-stats .attention{background:color-mix(in srgb,#da9344 12%,var(--canvas))}.dataset-stats span{font-size:12px;color:var(--muted)}.dataset-stats :deep(.el-statistic__content){font-size:29px;font-weight:700;margin-top:8px}.run-status{border:1px solid var(--line);border-radius:0;padding:14px;margin-bottom:16px}.run-status .section-heading{margin-bottom:8px}.error-text{color:var(--el-color-danger);overflow-wrap:anywhere}.dataset-error{display:flex;gap:10px;margin-bottom:16px}.mapping-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.mapping-grid .el-form-item{min-width:0}.length-options,.dataset-actions,.clean-summary{display:flex;align-items:center;flex-wrap:wrap;gap:14px;margin-top:18px}.length-options label{font-size:12px}.dataset-actions{padding-top:18px;border-top:1px solid var(--line)}.dataset-actions a{font-size:13px}.event-list{max-height:220px;overflow:auto;font-size:12px;line-height:1.9}.clean-summary{padding:16px;background:color-mix(in srgb,#329b8c 8%,var(--canvas));font-size:13px}.dataset-list .el-pagination{margin-top:16px}.dataset-welcome{min-height:360px}.dataset-detail{min-width:0}@media(max-width:1200px){.upload-form{grid-template-columns:repeat(2,minmax(0,1fr))}.dataset-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:950px){.dataset-layout{grid-template-columns:minmax(0,1fr)}.mapping-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.upload-form,.mapping-grid{grid-template-columns:minmax(0,1fr)}.dataset-upload,.dataset-list,.dataset-detail{padding:14px}.section-heading{flex-wrap:wrap}}
</style>
