<script setup lang="ts">
import RecordPagination from '../RecordPagination.vue'
import { onBeforeUnmount, ref, watch } from 'vue'
import { predictions, artifact, type PredictionPage } from '../../api/training'
const props = defineProps<{ runId: string; action: string; inputName?: string }>()
const result = ref<PredictionPage>(), page = ref(1), pageSize = ref(20), q = ref(''), predicted = ref(''), outcome = ref('all'), error = ref(''), loading = ref(false)
let sequence = 0, alive = true
const outcomes: Record<string, string> = { TP: '正确检出 TP', FP: '误报 FP', TN: '正确排除 TN', FN: '漏报 FN' }
async function load(reset = false) {
  if (reset) page.value = 1
  const token = ++sequence; loading.value = true; error.value = ''
  try {
    const value = await predictions(props.runId, page.value, pageSize.value, q.value.trim(), predicted.value || '', outcome.value)
    if (alive && token === sequence) result.value = value
  } catch (value) { if (alive && token === sequence) error.value = value instanceof Error ? value.message : '读取结果失败，请重试' }
  finally { if (alive && token === sequence) loading.value = false }
}
watch(() => props.runId, () => { result.value = undefined; q.value = ''; predicted.value = ''; outcome.value = 'all'; void load(true) }, { immediate: true })
onBeforeUnmount(() => { alive = false; sequence++ })
</script>
<template>
  <section class="work-panel"><div class="work-heading"><h2>{{ action === 'EVALUATE' ? '评价逐条结果' : '预测结果' }} · {{ result?.total?.toLocaleString() ?? '—' }} / {{ result?.count?.toLocaleString() ?? '—' }}条</h2><a :href="artifact(runId, 'predictions.jsonl')">下载全部结果</a></div>
    <p v-if="inputName" class="muted">源文件：{{ inputName }}</p>
    <p v-if="error" role="alert" class="work-error">{{ error }}</p>
    <div class="work-search"><el-input v-model="q" maxlength="120" placeholder="搜索编号或文本" aria-label="搜索预测结果" @keyup.enter="load(true)" /><el-select v-model="predicted" aria-label="预测类别" @change="load(true)"><el-option value="" label="全部预测类别" /><el-option value="1" label="预测复用" /><el-option value="0" label="预测非复用" /></el-select><el-select v-model="outcome" aria-label="对照标签筛选" @change="load(true)"><el-option value="all" label="全部标签对照" /><el-option v-for="(name, key) in outcomes" :key="key" :value="key" :label="name" /></el-select><el-button :loading="loading" @click="load(true)">查询</el-button></div>
    <el-table :data="result?.items ?? []" v-loading="loading" row-key="id" empty-text="没有符合筛选的结果"><el-table-column type="expand"><template #default="{row}"><div class="match-pair prediction-expanded"><div><strong>文本一</strong><p>{{ row.sentence1 }}</p></div><div><strong>文本二</strong><p>{{ row.sentence2 }}</p></div></div></template></el-table-column><el-table-column prop="id" label="编号" width="100" show-overflow-tooltip /><el-table-column prop="sentence1" label="文本一" min-width="200" show-overflow-tooltip /><el-table-column prop="sentence2" label="文本二" min-width="200" show-overflow-tooltip /><el-table-column label="得分" width="130"><template #default="{ row }">{{ row.score.toFixed(5) }}<small v-if="row.scoreType === 'margin'"> 间隔</small></template></el-table-column><el-table-column label="预测" width="110"><template #default="{ row }">{{ row.predicted === 1 ? '复用' : '非复用' }}</template></el-table-column><el-table-column label="标签" width="100"><template #default="{ row }">{{ row.label === undefined ? '—' : row.label === 1 ? '复用' : '非复用' }}</template></el-table-column><el-table-column label="对照" width="130"><template #default="{ row }">{{ row.outcome ? outcomes[row.outcome] : '—' }}</template></el-table-column></el-table>
    <RecordPagination v-model:current-page="page" v-model:page-size="pageSize" :total="result?.total ?? 0" @change="load()" />
  </section>
</template>

<style scoped>.prediction-expanded{padding:16px 22px;white-space:pre-wrap}</style>
