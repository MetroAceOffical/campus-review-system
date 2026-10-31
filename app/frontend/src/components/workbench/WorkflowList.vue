<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { listFlows,type Flow } from '../../api/flows'
import { flowDestination } from '../../flow-navigation'
import RecordPagination from '../RecordPagination.vue'
const rows=ref<Flow[]>([]),page=ref(1),size=ref(5),total=ref(0),q=ref(''),error=ref('')
async function load(){try{const result=await listFlows(page.value,size.value,q.value);rows.value=result.items;total.value=result.total;error.value=''}catch(e){error.value=e instanceof Error?e.message:'读取任务失败'}}
onMounted(load)
</script>
<template><section class="panel saved-flows"><div class="section-heading"><h2>我的任务</h2><el-input v-model="q" placeholder="搜索任务" aria-label="搜索我的任务" clearable @change="page=1;load()" /></div><p v-if="error" role="alert" class="work-error">{{error}}</p><el-table :data="rows" empty-text="从上方选择一项操作开始"><el-table-column prop="name" label="任务" min-width="180"/><el-table-column label="当前对象" min-width="200"><template #default="{row}">{{row.context.modelId?'已生成模型版本':row.context.trainingRunId?'已关联训练任务':row.context.importId?'已关联入库批次':row.context.datasetId?'已选择数据':row.context.parentModelId?'已选择起始模型':'待选择材料'}}</template></el-table-column><el-table-column label="最近操作" min-width="150"><template #default="{row}">{{new Date(row.updatedAt.replace(' ','T')+'Z').toLocaleString('zh-CN')}}</template></el-table-column><el-table-column label="操作" width="110"><template #default="{row}"><RouterLink class="link-button" :to="flowDestination(row)">恢复任务</RouterLink></template></el-table-column></el-table><RecordPagination v-model:current-page="page" v-model:page-size="size" :total="total" @change="load"/></section></template>
<style scoped>.section-heading>.el-input{max-width:240px}</style>
