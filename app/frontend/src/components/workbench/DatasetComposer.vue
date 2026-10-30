<script setup lang="ts">
import RecordPagination from '../RecordPagination.vue'
const pageSize = ref(12)
import { computed, ref, onMounted, watch } from 'vue'
import * as api from '../../api/workbench'
import type { Dataset, Detail } from '../../api/workbench'
const props = defineProps<{ organizations: Array<{ organizationId: string; name: string }> }>()
const emit = defineEmits<{ created: [datasetId: string] }>()
const q = ref(''), page = ref(1), total = ref(0), items = ref<Dataset[]>([]), candidate = ref<Detail>(), datasetId = ref(''), versionId = ref(''), name = ref(''), organizationId = ref(''), error = ref(''), busy = ref(false)
const sources = ref<Array<{ datasetId: string; versionId: string; name: string; kind: string; rows: number }>>([])
const versions = computed(() => candidate.value?.versions.filter(v => v.stage === 'CLEAN' && v.status === 'READY') ?? [])
const rows = computed(() => sources.value.reduce((sum, row) => sum + row.rows, 0))
async function perform(task: () => Promise<void>) { if (busy.value) return; busy.value = true; error.value = ''; try { await task() } catch (value) { error.value = value instanceof Error ? value.message : '组合未完成，请重试' } finally { busy.value = false } }
async function load() { const result = await api.datasets(page.value, q.value, false, pageSize.value); items.value = result.items; total.value = result.total }
async function choose() { candidate.value = undefined; versionId.value = ''; if (datasetId.value) { candidate.value = await api.dataset(datasetId.value); versionId.value = versions.value[0]?.versionId ?? '' } }
function add() {
  error.value = ''
  const data = candidate.value, version = versions.value.find(v => v.versionId === versionId.value)
  if (!data || !version) { error.value = '请选择已完成的清洗版本'; return }
  if (sources.value.length >= 10 || sources.value.some(s => s.datasetId === data.datasetId)) { error.value = '最多10个不同数据集，每个数据集选择一个版本'; return }
  if (sources.value.length && sources.value[0]!.kind !== data.kind) { error.value = '原始新闻与标签句对不能混合组合'; return }
  if (rows.value + (version.rowCount ?? 0) > 100000) { error.value = '组合后最多100000行，请分批组合'; return }
  sources.value = [...sources.value, { datasetId: data.datasetId, versionId: version.versionId, name: data.name, kind: data.kind, rows: version.rowCount ?? 0 }]
}
async function submit() { await perform(async () => { if (!name.value.trim() || !organizationId.value || sources.value.length < 2) throw new Error('请填写名称、目标部门，并选择至少两个来源'); const result = await api.compose(organizationId.value, name.value, sources.value.map(s => ({ datasetId: s.datasetId, versionId: s.versionId }))); emit('created', result.datasetId); sources.value = []; name.value = '' }) }
watch(() => props.organizations, value => { organizationId.value ||= value[0]?.organizationId ?? '' }, { immediate: true })
onMounted(() => void perform(load))
</script>
<template>
  <section class="work-panel"><details><summary>组合多个数据集</summary><p v-if="error" class="work-error" role="alert">{{ error }}</p>
    <div class="work-search"><el-input v-model="q" placeholder="搜索来源数据集" aria-label="搜索组合来源" @change="page = 1; perform(load)" /><el-button :loading="busy" @click="page = 1; perform(load)">搜索</el-button><RecordPagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" @change="perform(load)" /></div>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="来源数据集"><el-select v-model="datasetId" aria-label="组合来源数据集" @change="perform(choose)"><el-option v-for="item in items" :key="item.datasetId" :value="item.datasetId" :label="item.name" /><el-option v-if="candidate && !items.some(i => i.datasetId === candidate!.datasetId)" :value="candidate.datasetId" :label="candidate.name" /></el-select></el-form-item><el-form-item label="清洗版本"><el-select v-model="versionId" aria-label="组合来源版本"><el-option v-for="version in versions" :key="version.versionId" :value="version.versionId" :label="`${version.versionId.slice(0, 8)} · ${version.rowCount}行`" /></el-select></el-form-item><el-form-item label="添加来源"><el-button :disabled="!versionId || busy" @click="add">加入组合</el-button></el-form-item></div></el-form>
    <el-table :data="sources" row-key="datasetId" empty-text="选择至少两个同类型清洗数据集"><el-table-column prop="name" label="来源" /><el-table-column label="版本"><template #default="{ row }">{{ row.versionId.slice(0, 8) }}</template></el-table-column><el-table-column prop="rows" label="行数" /><el-table-column label="操作"><template #default="{ row }"><el-button link @click="sources = sources.filter(s => s.datasetId !== row.datasetId)">移除</el-button></template></el-table-column></el-table>
    <p class="muted">{{ sources.length }}个来源 · {{ rows.toLocaleString() }}行</p>
    <el-form label-position="top"><div class="work-grid"><el-form-item label="组合名称"><el-input v-model="name" maxlength="120" placeholder="例如：新闻中心综合语料" /></el-form-item><el-form-item label="保存到部门"><el-select v-model="organizationId"><el-option v-for="organization in organizations" :key="organization.organizationId" :value="organization.organizationId" :label="organization.name" /></el-select></el-form-item></div></el-form><div class="work-actions"><el-button type="primary" :loading="busy" :disabled="sources.length < 2" @click="submit">创建组合版本</el-button></div>
  </details></section>
</template>
