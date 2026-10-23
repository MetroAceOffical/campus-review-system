<script setup lang="ts">
import { computed } from 'vue'
import type { ExperimentBundle } from '../../api/experiments'
import { training } from './charts'
import ExperimentChart from './ExperimentChart.vue'
const props=defineProps<{bundle:ExperimentBundle;model:string}>()
const charts=computed(()=>training(props.bundle,props.model)),runs=computed(()=>props.bundle.history.runs.filter(r=>r.family===props.model))
</script>
<template><el-empty v-if="!runs.length" description="该传统模型无逐轮训练记录，可在配置比较中查看拟合时间与验证结果" /><template v-else><el-alert title="验证历史与测试口径无关；未记录验证 Loss，不补造曲线。达到轮数上限不代表收敛。" type="info" :closable="false" /><el-table :data="runs" size="small"><el-table-column label="配置"><template #default="{row}">{{ row.index }} {{ row.selected?'★ 所选':'' }}</template></el-table-column><el-table-column label="实际轮数"><template #default="{row}">{{ row.epochs.length }}</template></el-table-column><el-table-column prop="bestEpoch" label="最佳验证轮" /><el-table-column label="参数" min-width="300"><template #default="{row}"><code>{{ JSON.stringify(row.config) }}</code></template></el-table-column></el-table><div class="experiment-grid"><ExperimentChart v-for="chart in charts" :key="chart.title" v-bind="chart" /></div></template></template>
