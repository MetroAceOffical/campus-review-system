<script setup lang="ts">
import { onMounted,onBeforeUnmount,ref,watch } from 'vue'
import { init,use,type EChartsType,type EChartsCoreOption } from 'echarts/core'
import { BarChart,LineChart,ScatterChart,HeatmapChart,BoxplotChart,RadarChart,SankeyChart,ParallelChart } from 'echarts/charts'
import { GridComponent,TooltipComponent,LegendComponent,VisualMapComponent,DataZoomComponent,AriaComponent,RadarComponent,ParallelComponent,ToolboxComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
use([BarChart,LineChart,ScatterChart,HeatmapChart,BoxplotChart,RadarChart,SankeyChart,ParallelChart,GridComponent,TooltipComponent,LegendComponent,VisualMapComponent,DataZoomComponent,AriaComponent,RadarComponent,ParallelComponent,ToolboxComponent,CanvasRenderer])
const emit=defineEmits<{select:[point:any]}>()
const props=defineProps<{title:string;note?:string;option:EChartsCoreOption}>(),host=ref<HTMLElement>();let chart:EChartsType|undefined,resize:ResizeObserver|undefined,theme:MutationObserver|undefined
function restore(){chart?.dispatchAction({type:'restore'})}
function object(value:unknown):Record<string,unknown>{return value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{}}
function axes(value:unknown,defaults:Record<string,unknown>){return Array.isArray(value)?value.map(v=>({...defaults,...object(v)})):value?{...defaults,...object(value)}:undefined}
function draw(){if(!chart)return;const css=getComputedStyle(document.documentElement),color=css.color,line=css.getPropertyValue('--line'),primary=css.getPropertyValue('--el-color-primary')||'#215dba'
  chart.setOption({animation:false,textStyle:{color,fontFamily:'Microsoft YaHei,sans-serif'},color:[primary,'#da9344','#329b8c','#b67ccc','#d36c7a','#749cce'],...props.option,
    legend:{top:6,textStyle:{color},type:'scroll',icon:'rect',...object(props.option.legend)},
    xAxis:axes(props.option.xAxis,{axisLabel:{color},axisLine:{lineStyle:{color:line}}}),
    yAxis:axes(props.option.yAxis,{axisLabel:{color},splitLine:{lineStyle:{color:line}}}),
    ...(props.option.radar?{radar:{...object(props.option.radar),axisName:{color},axisLine:{lineStyle:{color:line}},splitLine:{lineStyle:{color:line}}}}:{}),
    ...(Array.isArray(props.option.parallelAxis)?{parallelAxis:props.option.parallelAxis.map(axis=>({...object(axis),nameTextStyle:{color},axisLabel:{color},axisLine:{lineStyle:{color:line}}}))}:{}),
    tooltip:{trigger:'axis',confine:true,renderMode:'richText',borderRadius:0,...object(props.option.tooltip)}},true)
}
onMounted(()=>{chart=init(host.value!);chart.on('click',point=>emit('select',point));draw();resize=new ResizeObserver(()=>chart?.resize());resize.observe(host.value!);theme=new MutationObserver(draw);theme.observe(document.documentElement,{attributes:true,attributeFilter:['class','style']})})
watch(()=>props.option,draw,{deep:false});onBeforeUnmount(()=>{resize?.disconnect();theme?.disconnect();chart?.dispose()})
</script>
<template><figure class="experiment-chart"><div class="chart-heading"><h3>{{ title }}</h3><div class="chart-actions"><button type="button" :aria-label="`恢复${title}视图`" @click="restore">恢复视图</button></div></div><div ref="host" class="chart-canvas" role="img" :aria-label="title" /><figcaption v-if="note">{{ note }}</figcaption></figure></template>
<style scoped>.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}.chart-actions{display:flex;gap:6px}.chart-actions button{border:1px solid var(--line);border-radius:0;background:transparent;color:inherit;font-size:12px;padding:4px 8px;cursor:pointer}.chart-actions button:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:2px}</style>
