<script setup lang="ts">
import { computed } from 'vue'
import type { ExperimentBundle } from '../../api/experiments'
import { comparison } from './charts'
import ExperimentChart from './ExperimentChart.vue'
const props=defineProps<{bundle:ExperimentBundle;model:string}>()
const charts=computed(()=>comparison(props.bundle,props.model)),rows=computed(()=>props.bundle.search.configurations.filter(r=>r.family===props.model))
</script>
<template><div class="experiment-grid"><ExperimentChart v-for="chart in charts" :key="chart.title" v-bind="chart" /></div><el-table :data="rows" size="small"><el-table-column label="配置"><template #default="{row}">{{ row.index }} {{ row.selected?'★ 所选':'' }}</template></el-table-column><el-table-column label="验证 Macro-F1"><template #default="{row}">{{ row.validation_macro_f1.toFixed(8) }}</template></el-table-column><el-table-column prop="fit_or_train_seconds" label="拟合 / 训练秒数" /><el-table-column label="参数" min-width="300"><template #default="{row}"><code>{{ JSON.stringify(row.config) }}</code></template></el-table-column></el-table></template>
