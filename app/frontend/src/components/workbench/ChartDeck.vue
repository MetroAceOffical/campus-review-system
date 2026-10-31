<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import type {ChartSpec} from '../../training-charts'
import ExperimentChart from '../experiments/ExperimentChart.vue'
const props=defineProps<{charts:ChartSpec[];defaultGroup?:string}>(),emit=defineEmits<{select:[key:string,point:any]}>()
const active=ref(props.defaultGroup||'')
const groups=computed(()=>[...new Set(props.charts.map(c=>c.group))])
watch(groups,g=>{if(!g.includes(active.value))active.value=g[0]||''},{immediate:true})
const shown=computed(()=>props.charts.filter(c=>c.group===active.value)),missing=computed(()=>shown.value.filter(c=>!c.ready))
</script>
<template><section class="chart-deck"><el-tabs v-if="groups.length>1" v-model="active" class="workspace-tabs"><el-tab-pane v-for="g in groups" :key="g" :name="g" :label="g"/></el-tabs><div class="experiment-grid"><ExperimentChart v-for="chart in shown.filter(c=>c.ready)" :key="chart.key" :title="chart.title" :note="chart.note" :option="chart.option" @select="point=>emit('select',chart.key,point)"/></div><div v-if="missing.length" class="chart-pending"><div v-for="chart in missing" :key="chart.key"><strong>{{chart.title}}</strong><span>{{chart.empty||'完成相应评价后显示'}}</span></div></div></section></template>
<style scoped>.chart-pending{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:8px 0}.chart-pending>div{display:flex;gap:8px;align-items:center;flex-wrap:wrap;border:1px dashed var(--line);padding:10px 12px;font-size:12px}.chart-pending strong{font-weight:500}.chart-pending span{color:var(--muted)}@media(max-width:750px){.chart-pending{grid-template-columns:1fr}}</style>
