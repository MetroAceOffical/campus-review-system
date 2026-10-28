<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formalProgress, type FormalProgress, type FormalStage, type FormalPoint } from '../../api/training'
import ExperimentChart from '../experiments/ExperimentChart.vue'

const data = ref<FormalProgress>(), error = ref(''), loading = ref(false)
const observations = ref<Array<{ at: string; accepted: number; quarantined: number }>>([])
let timer: ReturnType<typeof setInterval> | undefined, alive = true
const names: Record<string, string> = {
  PENDING: '未启动', NOT_STARTED: '未启动', READ_ERROR: '读取中', RUNNING_CHILD: '流程运行中',
  GENERATING_TRAIN_MATERIAL: '生成与检查', TRAINING: '训练中', CORRESPONDENCE_TRAINING: '训练中',
  CAMPUS_RETRIEVAL_TRAINING_COMPLETE: '训练与重载完成', CORRESPONDENCE_TRAINING_COMPLETE: '训练与重载完成',
  WAITING_CAMPUS_TRAINING_COMPLETION: '等待校园模型训练', WAITING_FORMAL_MATERIAL: '等待训练材料',
  QUERY_CONSTRUCTION_PLAN_AND_EXACT_CONTROLS_FROZEN: '评价材料准备中', STAGE_STOPPED: '流程已停止',
  FORMAL_MATERIAL_COMPLETE: '正式材料已准备', CORRECTED_MATERIAL_READY: '正式材料已准备',
  FORMAL_MATERIAL_READY: '正式材料已准备', TRAIN_CONSTRUCTION_FINISHED: '样本准备已完成',
  WAITING_CORRECTED_CANDIDATES: '等待候选挖掘', WAITING_WEB_OR_GPU_RESOURCE: '等待计算资源',
  WAITING_OTHER_GPU_CONSUMER: '等待计算资源', WAITING_GPU_RESOURCE: '等待计算资源',
  LAUNCHING_OFFLINE_CHILD: '启动训练阶段', RETRIEVER_PENDING_SUPPORTED_GROUPS: '检索分组待补充',
  NEEDS_MORE_INDEPENDENT_SOURCES_OR_EVENTS: '原稿或事件数量待补充',
  CAMPUS_TRAINING_AND_EXPORT_COMPLETE: '两模型训练与导出完成', M3_TRAINING_AND_EXPORT_COMPLETE_RETRIEVER_PENDING: 'M3已导出，BGE材料待补充',
  TRAINING_CONTROLLER_RETURNED: '训练流程已返回', MATERIAL_PIPELINE_STOPPED: '材料流程已停止',
  GENERATION_FAILED: '样本准备失败', LOADING_HELDOUT_GENERATOR: '加载评价材料生成器',
  GENERATING_HELDOUT_QUERIES: '构造独立评价材料', HELDOUT_SEGMENT_GENERATION_FINISHED: '评价改写段已生成',
  HELDOUT_GENERATION_STOPPED: '评价材料流程已停止', HELDOUT_QUERY_MATERIAL_ASSEMBLED: '评价材料已组装', OBSERVED: '已读取',
  LOADING_IMAGE_EVALUATION: '加载图片评价模型', RUNNING_IMAGE_DEVELOPMENT_EVALUATION: '图片开发区评价中',
  IMAGE_DEVELOPMENT_EVALUATION_COMPLETE: '图片开发区评价完成', IMAGE_EVALUATION_STOPPED: '图片评价已停止',
  WAITING_HOST_MEMORY: '等待可用内存', WAITING_CPU_EVALUATOR: '等待CPU评价任务',
  RUNNING_DOCUMENT_EVALUATION: '文稿检查评价中', DOCUMENT_EVALUATION_COMPLETE: '开发评价完成', DOCUMENT_EVALUATION_STOPPED: '文稿评价已停止',
}
const generation = computed(() => data.value?.stages.find(s => s.key === 'generation'))
const protocol = computed(() => data.value?.stages.find(s => s.key === 'protocol'))
const imageEvaluation = computed(() => data.value?.stages.find(s => s.key === 'image_evaluation'))
const grammarEvaluations = computed(() => data.value?.stages.filter(s => ['grammar_rules', 'grammar_model'].includes(s.key)) ?? [])
const fieldsBefore = computed(() => data.value?.stages.find(s => s.key === 'image_fields_before'))
const fieldsAfter = computed(() => data.value?.stages.find(s => s.key === 'image_fields'))
const imageTextEvaluation = computed(() => data.value?.stages.find(s => s.key === 'image_text_evaluation'))
const models = computed(() => data.value?.stages.filter(s => ['bge', 'm3'].includes(s.key)) ?? [])
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const count = (value: unknown) => finite(value) ? value.toLocaleString() : '—'
const metric = (stage: FormalStage | undefined, key: string) => stage?.metrics?.[key]
const moment = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '—'
const duration = (value: unknown) => finite(value) ? value >= 3600 ? `${(value / 3600).toFixed(1)}小时` : `${Math.round(value / 60)}分钟` : '—'
const number = (value: unknown) => finite(value) ? value.toFixed(5) : '—'
const memory = (value: unknown) => finite(value) ? `${(value / 1024 ** 3).toFixed(2)} GiB` : '—'
const splitNames: Record<string, string> = { calibration: '校准', dev: '开发', final: '最终评价' }
const parameterNames: Record<string, string> = { epochs: '轮数', microbatch: '单步样本', effectiveQueries: '有效查询批量', effectivePairs: '有效配对批量', maxTokensPerSide: '每侧Token上限', maxJointTokens: '联合Token上限', explicitNegatives: '每查询负例数', learningRate: '学习率', loraR: 'LoRA秩', loraAlpha: 'LoRA缩放', dropout: 'Dropout', adapterLearningRate: '适配器学习率', headLearningRate: '分类头学习率' }
function state(stage: FormalStage) { return stage.availability === 'READ_ERROR' ? '读取中' : names[stage.state] ?? stage.state }
function points(stage: FormalStage) { return stage.history.filter(row => finite(row.step) && finite(row.loss)) }
async function refresh() {
  if (loading.value) return
  loading.value = true
  try {
    const result = await formalProgress()
    if (!alive) return
    data.value = result; error.value = ''
    const stage = result.stages.find(s => s.key === 'generation'), accepted = metric(stage, 'accepted'), quarantined = metric(stage, 'quarantined')
    if (stage?.updatedAt && finite(accepted) && finite(quarantined) && observations.value.at(-1)?.at !== stage.updatedAt) {
      observations.value = [...observations.value, { at: stage.updatedAt, accepted, quarantined }].slice(-600)
    }
  } catch (value) { if (alive) error.value = value instanceof Error ? value.message : '进度读取失败，请刷新重试' }
  finally { if (alive) loading.value = false }
}
const chart = { grid: { left: 60, right: 25, bottom: 52, top: 45 }, tooltip: { trigger: 'axis', borderRadius: 0 }, aria: { enabled: true }, dataZoom: [{ type: 'inside' }, { type: 'slider', height: 12, bottom: 3 }] }
const samples = computed(() => ({ ...chart, legend: { data: ['合格段落', '隔离段落'] }, xAxis: { type: 'category', data: observations.value.map(p => new Date(p.at).toLocaleTimeString('zh-CN')) }, yAxis: { type: 'value' }, series: [
  { name: '合格段落', type: 'line', showSymbol: observations.value.length === 1, data: observations.value.map(p => p.accepted) },
  { name: '隔离段落', type: 'line', showSymbol: observations.value.length === 1, data: observations.value.map(p => p.quarantined) },
] }))
const partitions = computed(() => ({ ...chart, legend: { data: ['已构造', '待补充'] }, xAxis: { type: 'category', data: protocol.value?.splits?.map(s => splitNames[s.split] ?? s.split) ?? [] }, yAxis: { type: 'value' }, series: ['constructed', 'pending'].map(key => ({ name: key === 'constructed' ? '已构造' : '待补充', type: 'bar', stack: 'queries', data: protocol.value?.splits?.map(s => s[key as 'constructed' | 'pending']) ?? [] })) }))
const imageCounts = computed(() => ({ ...chart, xAxis: { type: 'category', data: ['DINO Top10', 'DINO Top20', '组合检出', '区域类型正确'] }, yAxis: { type: 'value', minInterval: 1 }, series: [{ name: '正确来源数量', type: 'bar', data: ['baselineAccepted', 'top20Accepted', 'enhancedAccepted', 'scopeCorrect'].map(key => metric(imageEvaluation.value, key) ?? null) }] }))
const fieldCounts = computed(() => ({ ...chart, legend: { data: ['正确字段', '误报冲突'] }, xAxis: { type: 'category', data: ['旧解析', '新解析'] }, yAxis: { type: 'value', minInterval: 1 }, series: ['correctFields', 'falseConflicts'].map((key, i) => ({ name: i === 0 ? '正确字段' : '误报冲突', type: 'bar', data: [fieldsBefore.value, fieldsAfter.value].map(stage => metric(stage, key) ?? null) })) }))
function editCounts(stage: FormalStage) { return { ...chart, xAxis: { type: 'category', data: ['检出', '多报', '漏报'] }, yAxis: { type: 'value', minInterval: 1 }, series: [{ name: '编辑数量', type: 'bar', data: ['truePositive', 'falsePositive', 'falseNegative'].map(key => metric(stage, key) ?? null) }] } }
function loss(stage: FormalStage) {
  const training = points(stage), validation = stage.history.filter(p => finite(p.step) && finite(p.validationLoss))
  return { ...chart, legend: { data: ['训练损失', '验证损失'] }, xAxis: { type: 'value', name: 'Step', minInterval: 1 }, yAxis: { type: 'value', name: 'Loss', scale: true }, series: [
    { name: '训练损失', type: 'line', showSymbol: training.length === 1, data: training.map(p => [p.step, p.loss]) },
    { name: '验证损失', type: 'line', connectNulls: false, data: validation.map(p => [p.step, p.validationLoss]) },
  ] }
}
function resources(stage: FormalStage) {
  const rows = stage.history.filter(p => finite(p.step) && finite(p.cudaPeakAllocatedBytes ?? p.cudaPeakBytes))
  return { ...chart, xAxis: { type: 'value', name: 'Step', minInterval: 1 }, yAxis: { type: 'value', name: 'GiB', scale: true }, series: [{ name: '峰值显存', type: 'line', showSymbol: rows.length === 1, data: rows.map(p => [p.step, (p.cudaPeakAllocatedBytes ?? p.cudaPeakBytes)! / 1024 ** 3]) }] }
}
function latest(stage: FormalStage): FormalPoint { return finite(stage.latest?.loss) ? stage.latest : [...stage.history].reverse().find(p => finite(p.loss)) ?? stage.latest ?? {} }
onMounted(() => { void refresh(); timer = setInterval(() => void refresh(), 5000) })
onBeforeUnmount(() => { alive = false; if (timer) clearInterval(timer) })
</script>
<template>
  <section class="work-panel" aria-label="校级正式训练进度">
    <div class="work-heading"><div><h2>{{ data?.title || '校级正式模型训练' }}</h2><span class="muted">每5秒更新 · {{ moment(data?.observedAt) }}</span></div><el-button :loading="loading" @click="refresh">刷新进度</el-button></div>
    <p v-if="error" role="alert" class="work-error">{{ error }}</p>
    <p v-else-if="!data" role="status">正在读取训练进度…</p>
    <template v-if="data">
      <div class="work-stats"><div><span>处理原稿</span><strong>{{ count(data.recipe.generationOriginals) }}</strong></div><div><span>计划段落窗口</span><strong>{{ count(data.recipe.generationSegments) }}</strong></div><div><span>BGE / M3 训练轮数</span><strong>{{ count(data.recipe.epochsBge) }} <small>/ {{ count(data.recipe.epochsM3) }}</small></strong></div></div>
      <p class="muted">目标：{{ count(data.recipe.minimumPairs) }}条对应句对 · {{ count(data.recipe.minimumRetrievalGroups) }}组检索查询 · 有效批量 {{ count(data.recipe.effectiveBatch) }}</p>
      <details v-if="data.recipe.training"><summary>正式训练配置</summary><div v-for="(parameters, family) in data.recipe.training" :key="family"><h3>{{ family === 'bge' ? 'BGE' : 'M3' }}</h3><el-descriptions border :column="2"><el-descriptions-item v-for="(value, key) in parameters" :key="key" :label="parameterNames[key] || key">{{ value }}</el-descriptions-item></el-descriptions></div></details>
      <el-table :data="data.stages" row-key="key" aria-label="正式流程阶段"><el-table-column prop="title" label="阶段" min-width="160" /><el-table-column label="状态" min-width="150"><template #default="{ row }"><el-tag :type="row.availability === 'READ_ERROR' ? 'warning' : 'info'">{{ state(row) }}</el-tag><span v-if="row.stale" class="muted"> · 进度待更新</span></template></el-table-column><el-table-column label="处理量" min-width="130"><template #default="{ row }">{{ count(row.progress?.processed) }} / {{ count(row.progress?.total) }}</template></el-table-column><el-table-column label="进度更新时间" min-width="180"><template #default="{ row }">{{ moment(row.updatedAt) }}</template></el-table-column></el-table>
      <template v-if="generation"><h3>新闻样本准备</h3><div class="work-stats"><div><span>合格段落</span><strong>{{ count(metric(generation, 'accepted')) }}</strong></div><div><span>隔离 / 待处理</span><strong>{{ count(metric(generation, 'quarantined')) }} <small>/ {{ count(metric(generation, 'pending')) }}</small></strong></div><div><span>已复用段落</span><strong>{{ count(metric(generation, 'reused')) }}</strong></div></div>
        <el-progress v-if="finite(generation.progress?.percent)" :percentage="Math.min(100, Math.max(0, generation.progress!.percent!))" />
        <p class="muted">已用时 {{ duration(metric(generation, 'elapsedSeconds')) }} · 按当前速度估计剩余 {{ duration(metric(generation, 'estimatedRemainingSeconds')) }} · 峰值显存 {{ memory(metric(generation, 'cudaPeakAllocatedBytes')) }}</p>
        <ExperimentChart v-if="observations.length" title="实时样本准备数量" :option="samples as any" />
      </template>
      <div v-for="model in models" :key="model.key" class="formal-model"><h3>{{ model.title }}</h3><div class="work-stats"><div><span>实际轮数 / Step</span><strong>{{ count(latest(model).epoch ?? metric(model, 'epochs')) }} <small>/ {{ count(latest(model).step ?? metric(model, 'steps')) }}</small></strong></div><div><span>最新训练损失</span><strong class="stage-value">{{ number(latest(model).loss) }}</strong></div><div><span>执行状态</span><strong class="stage-value">{{ state(model) }}</strong></div></div><div class="experiment-grid" v-if="points(model).length"><ExperimentChart :title="`${model.title}损失`" :option="loss(model) as any" /><ExperimentChart :title="`${model.title}资源`" :option="resources(model) as any" /></div><p v-else class="muted">训练开始后显示实际损失与资源记录。</p></div>
      <template v-if="protocol?.splits?.length"><h3>独立评价材料</h3><ExperimentChart title="评价查询构造进度" :option="partitions as any" /><el-table :data="protocol.splits" aria-label="评价分区准备"><el-table-column label="分区"><template #default="{ row }">{{ splitNames[row.split] || row.split }}</template></el-table-column><el-table-column prop="target" label="目标数量" /><el-table-column prop="constructed" label="已构造" /><el-table-column prop="pending" label="待补充" /><el-table-column prop="constructedHomePrimaryQueries" label="已构造本校查询" /></el-table></template>
      <template v-if="imageEvaluation"><h3>图片开发区评价</h3><div class="work-stats"><div><span>已处理 / 总查询</span><strong>{{ count(metric(imageEvaluation, 'processed')) }} <small>/ {{ count(metric(imageEvaluation, 'total')) }}</small></strong></div><div><span>组合检出 / DINO Top10</span><strong>{{ count(metric(imageEvaluation, 'enhancedAccepted')) }} <small>/ {{ count(metric(imageEvaluation, 'baselineAccepted')) }}</small></strong></div><div><span>执行失败 / 覆盖不完整</span><strong>{{ count(metric(imageEvaluation, 'failedQueries')) }} <small>/ {{ count(metric(imageEvaluation, 'partialQueries')) }}</small></strong></div></div><p class="muted">{{ state(imageEvaluation) }} · 已用时 {{ duration(metric(imageEvaluation, 'elapsedSeconds')) }} · 预计剩余 {{ duration(metric(imageEvaluation, 'estimatedRemainingSeconds')) }} · 按正确原图统计</p><ExperimentChart v-if="finite(metric(imageEvaluation, 'processed')) && (metric(imageEvaluation, 'processed') as number) > 0" title="正确来源检出数量" :option="imageCounts as any" /></template>
      <div v-for="stage in grammarEvaluations" :key="stage.key"><h3>{{ stage.title }}</h3><div class="work-stats"><div><span>已处理 / 控制样本</span><strong>{{ count(metric(stage, 'processed')) }} <small>/ {{ count(metric(stage, 'total')) }}</small></strong></div><div><span>正确编辑 / 漏检</span><strong>{{ count(metric(stage, 'truePositive')) }} <small>/ {{ count(metric(stage, 'falseNegative')) }}</small></strong></div><div><span>执行状态</span><strong class="stage-value">{{ state(stage) }}</strong></div></div><p v-if="stage.state === 'WAITING_HOST_MEMORY'" class="muted">当前可用 {{ memory(metric(stage, 'availableMemoryBytes')) }} · 启动需求 {{ memory(metric(stage, 'requiredMemoryBytes')) }}</p><p v-if="finite(metric(stage, 'steps'))" class="muted">本批已处理句子 {{ count(metric(stage, 'steps')) }} / {{ count(metric(stage, 'totalSteps')) }}</p><ExperimentChart v-if="(metric(stage, 'processed') as number) > 0" :title="`${stage.title}编辑计数`" :option="editCounts(stage) as any" /></div>
      <template v-if="fieldsAfter"><h3>图文字段开发诊断</h3><div class="work-stats"><div><span>正确 / 有真值字段</span><strong>{{ count(metric(fieldsAfter, 'correctFields')) }} <small>/ {{ count(metric(fieldsAfter, 'assessableFields')) }}</small></strong></div><div><span>检出 / 预设冲突</span><strong>{{ count(metric(fieldsAfter, 'detectedConflicts')) }} <small>/ {{ count(metric(fieldsAfter, 'conflictFields')) }}</small></strong></div><div><span>误报冲突</span><strong>{{ count(metric(fieldsAfter, 'falseConflicts')) }}</strong></div></div><p class="muted">复用OCR开发识别结果 · 按合成通知的日期与地点统计</p><ExperimentChart title="图文字段开发诊断" :option="fieldCounts as any" /></template>
      <template v-if="imageTextEvaluation"><h3>完整图文检查开发评价</h3><div class="work-stats"><div><span>已处理 / 图文输入</span><strong>{{ count(metric(imageTextEvaluation, 'processed')) }} <small>/ {{ count(metric(imageTextEvaluation, 'total')) }}</small></strong></div><div><span>已知语境Top1 / 查询</span><strong>{{ count(metric(imageTextEvaluation, 'relatedTop1')) }} <small>/ {{ count(metric(imageTextEvaluation, 'knownContextQueries')) }}</small></strong></div><div><span>执行状态</span><strong class="stage-value">{{ state(imageTextEvaluation) }}</strong></div></div><p v-if="imageTextEvaluation.state === 'WAITING_HOST_MEMORY'" class="muted">当前可用 {{ memory(metric(imageTextEvaluation, 'availableMemoryBytes')) }} · 启动需求 {{ memory(metric(imageTextEvaluation, 'requiredMemoryBytes')) }}</p></template>
    </template>
  </section>
</template>
