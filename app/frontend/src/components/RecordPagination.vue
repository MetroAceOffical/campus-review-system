<script setup lang="ts">
import { ref, watch } from 'vue'
const props = withDefaults(defineProps<{ currentPage: number; pageSize: number; total: number }>(), { total: 0 })
const emit = defineEmits<{ 'update:currentPage': [value:number]; 'update:pageSize': [value:number]; change: []; 'current-change': [value:number]; 'size-change': [value:number] }>()
const requestedSize = ref(props.pageSize)
const requestedPage = ref(props.currentPage)
watch(() => props.pageSize, value => { requestedSize.value = value })
watch(() => props.currentPage, value => { requestedPage.value = value })
function resize() {
  const size=Number(requestedSize.value)
  if (!Number.isInteger(size) || size<1 || size>100) { requestedSize.value=props.pageSize; return }
  if (size===props.pageSize) return
  emit('update:pageSize',size); emit('update:currentPage',1); emit('size-change',size); emit('change')
}
function goTo(page: number) {
  if (page===props.currentPage) return
  emit('update:currentPage',page); emit('current-change',page); emit('change')
}
function jump() {
  const page=Number(requestedPage.value)
  if (!Number.isInteger(page)) { requestedPage.value=props.currentPage; return }
  const target=Math.max(1,Math.min(page,Math.max(1,Math.ceil(props.total/props.pageSize))))
  requestedPage.value=target; goTo(target)
}
</script>
<template><div class="record-pagination"><label class="record-size">每页 <input v-model.number="requestedSize" type="number" min="1" max="100" step="1" inputmode="numeric" aria-label="自定义每页条数（1至100）" title="每页可设置1至100条" @change="resize" @keydown.enter.prevent="resize" /> 条 <button type="button" @click="resize">应用</button></label><el-pagination :current-page="currentPage" :page-size="pageSize" :total="total" :pager-count="5" layout="total, prev, pager, next" @update:current-page="goTo" /><label class="record-size">跳至 <input v-model.number="requestedPage" type="number" min="1" :max="Math.max(1,Math.ceil(total/pageSize))" step="1" inputmode="numeric" aria-label="跳转页码" @keydown.enter.prevent="jump" /> 页 <button type="button" @click="jump">跳转</button></label></div></template>
<style scoped>.record-pagination{display:flex;align-items:center;justify-content:flex-end;gap:16px;flex-wrap:wrap;padding:16px 0 2px}.record-pagination :deep(.el-pagination){margin:0;max-width:100%;min-width:0;flex-wrap:wrap;row-gap:8px}.record-size{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:7px;white-space:nowrap}.record-size input{font:inherit;color:inherit;border:1px solid var(--line);background:var(--canvas);width:64px;height:30px;padding:4px 7px;border-radius:0}.record-size button{border:1px solid var(--line);background:var(--canvas);color:inherit;font-size:12px;padding:4px 8px;height:30px;cursor:pointer;border-radius:0}.record-size button:hover{color:var(--el-color-primary);border-color:var(--el-color-primary)}.record-size input:focus{outline:1px solid var(--el-color-primary)}@media(max-width:650px){.record-pagination{justify-content:flex-start;gap:10px}.record-pagination :deep(.el-pagination){white-space:normal;gap:3px;justify-content:flex-start}}</style>
