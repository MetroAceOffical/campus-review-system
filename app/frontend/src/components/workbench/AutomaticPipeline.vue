<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { Detail } from '../../api/workbench'
import * as api from '../../api/training'
import { modelNames } from '../../api/training'
const props = defineProps<{ dataset: Detail | null; versionId: string; models: api.PipelineModel[]; preparation: Record<string, unknown>; generation: Record<string, unknown>; name: string }>()
const emit = defineEmits<{ view: [runId: string] }>()
const source = ref(''), evaluate = ref(true), items = ref<api.Pipeline[]>([]), error = ref(''), busy = ref(false), page = ref(1), total = ref(0)
const following = ref(''), displayedRun = ref('')
const cleaning = ref({ strip_html: true, normalize_whitespace: true, remove_duplicates: true, min_text_length: 1, max_text_length: 1000000 })
const versions = computed(() => props.dataset?.versions.filter(v => v.status === 'READY' && !(v.stage === 'RAW' && v.origin === 'COMPOSITION')) ?? [])
const selectedModelNames = computed(() => props.models.map(model => modelNames[model.family]).join('、') || '请在下方选择模型')
let timer: ReturnType<typeof setInterval> | undefined, alive = true, refreshing = false
const states: Record<string, string> = { QUEUED: '排队中', RUNNING: '流程进行中', COMPLETED: '已完成', FAILED: '阶段失败', BLOCKED: '材料待补充', CANCELLED: '已取消', INTERRUPTED: '已中断' }
const stages: Record<string, string> = { CLEAN: '清洗', PREPARE: '分组与划分', GENERATE: '新闻样本准备', TRAIN: '训练', EVALUATE: '评价', DONE: '全部阶段完成', BLOCKED: '材料待补充' }
async function load() {
  const dataset = props.dataset?.datasetId, requested = page.value
  if (!dataset || refreshing) return
  refreshing = true
  try { const result = await api.pipelines(dataset, requested); if (alive && props.dataset?.datasetId === dataset && page.value === requested) { items.value = result.items; total.value = result.total; error.value = ''; showCurrent() } }
  catch (value) { if (alive && props.dataset?.datasetId === dataset) error.value = value instanceof Error ? value.message : '流程读取失败' }
  finally { refreshing = false }
}
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task(); await load() } catch (value) { error.value = value instanceof Error ? value.message : '流程操作失败' } finally { busy.value = false } }
async function start() { await perform(async () => {
  if (!props.dataset || !source.value || !props.models.length || !props.name.trim()) throw new Error('请选择数据版本、模型，并填写实验名称')
  const audited = props.dataset.runs.find(run => run.action === 'AUDIT' && run.inputVersionId === source.value && run.status === 'COMPLETED')
  const created = await api.startPipeline({ datasetId: props.dataset.datasetId, versionId: source.value, name: props.name, mapping: audited?.result?.mapping ?? {}, cleaning: cleaning.value, preparation: props.preparation, generation: props.generation, models: props.models, evaluate: evaluate.value })
  following.value = created.pipelineId; displayedRun.value = ''; page.value = 1
}) }
const control = (id: string, action: 'cancel' | 'retry') => perform(async () => { await api.controlPipeline(id, action) })
function showCurrent() { const run = items.value.find(item => item.pipelineId === following.value)?.state.currentRunId; if (run && run !== displayedRun.value) { displayedRun.value = run; emit('view', run) } }
function follow(id: string) { following.value = following.value === id ? '' : id; displayedRun.value = ''; showCurrent() }
watch(() => props.dataset?.datasetId, () => { page.value = 1; items.value = []; total.value = 0; source.value = versions.value.some(v => v.versionId === props.versionId) ? props.versionId : versions.value[0]?.versionId ?? ''; void load(); if (timer) clearInterval(timer); timer = setInterval(() => void load(), 2500) }, { immediate: true })
watch(versions, value => { if (!value.some(v => v.versionId === source.value)) source.value = value[0]?.versionId ?? '' })
onBeforeUnmount(() => { alive = false; if (timer) clearInterval(timer) })
</script>
<template>
  <section v-if="dataset" class="work-panel"><div class="work-heading"><div><h2>一键自动流程</h2><span class="muted">沿用本页所选模型与参数，按阶段自动衔接。</span></div><el-button :loading="busy" @click="load">刷新流程</el-button></div>
    <p v-if="error" class="work-error" role="alert">{{ error }}</p>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="起始数据版本"><el-select v-model="source" aria-label="自动流程起始版本"><el-option v-for="version in versions" :key="version.versionId" :value="version.versionId" :label="`${version.stage === 'RAW' ? '原始文件' : '清洗版本'} · ${version.versionId.slice(0, 8)}`" /></el-select></el-form-item><el-form-item label="将运行的模型"><span>{{ selectedModelNames }}</span></el-form-item><el-form-item label="训练后操作"><el-checkbox v-model="evaluate">自动在测试集评价</el-checkbox></el-form-item></div></el-form>
    <details><summary>原始文件清洗配置</summary><el-checkbox v-model="cleaning.strip_html">提取HTML正文</el-checkbox><el-checkbox v-model="cleaning.normalize_whitespace">规范空白</el-checkbox><el-checkbox v-model="cleaning.remove_duplicates">合并精确重复</el-checkbox><div class="work-grid"><el-form label-position="top"><el-form-item label="最小正文字数"><el-input-number v-model="cleaning.min_text_length" :min="1" :max="1000000" /></el-form-item></el-form><el-form label-position="top"><el-form-item label="最大正文字数"><el-input-number v-model="cleaning.max_text_length" :min="cleaning.min_text_length" :max="1000000" /></el-form-item></el-form></div></details>
    <p class="muted">{{ dataset.kind === 'NEWS' ? '清洗 → 分组 → 新闻样本准备 → 训练 → 评价' : '清洗 → 分组划分 → 训练 → 评价' }}</p><el-button type="primary" :loading="busy" :disabled="!source || !models.length || dataset.archived" @click="start">开始自动流程</el-button>
    <div v-for="pipeline in items" :key="pipeline.pipelineId"><div class="work-heading"><h3>{{ pipeline.name }}</h3><el-tag>{{ states[pipeline.status] || pipeline.status }} · {{ stages[pipeline.state.stage] || pipeline.state.stage }}</el-tag></div><p v-if="pipeline.error" class="work-error" role="alert">{{ pipeline.error }}</p>
      <el-table :data="pipeline.state.steps" row-key="runId" empty-text="准备派发首个阶段"><el-table-column label="阶段"><template #default="{ row }">{{ stages[row.stage] }} {{ modelNames[row.family] || '' }}</template></el-table-column><el-table-column label="状态"><template #default="{ row }">{{ states[row.status] || row.status }}</template></el-table-column><el-table-column label="查看实际进度"><template #default="{ row }"><el-button link @click="emit('view', row.runId)">日志与图表</el-button></template></el-table-column></el-table>
      <div class="work-actions"><el-button @click="follow(pipeline.pipelineId)">{{ following === pipeline.pipelineId ? '停止跟随' : '跟随阶段进度' }}</el-button><RouterLink v-if="pipeline.state.cleanVersionId" :to="{ path: '/datasets', query: { dataset: pipeline.datasetId, version: pipeline.state.cleanVersionId } }">清洗指标</RouterLink><el-button v-if="['QUEUED', 'RUNNING'].includes(pipeline.status)" :disabled="busy" @click="control(pipeline.pipelineId, 'cancel')">取消后续流程</el-button><el-button v-if="['FAILED', 'CANCELLED'].includes(pipeline.status)" :disabled="busy" @click="control(pipeline.pipelineId, 'retry')">重试当前阶段</el-button><RouterLink v-if="pipeline.state.models.length" to="/models">查看已完成模型</RouterLink></div>
    </div><el-pagination v-if="total" v-model:current-page="page" :total="total" :page-size="10" layout="total,prev,pager,next" @current-change="load" />
  </section>
</template>
