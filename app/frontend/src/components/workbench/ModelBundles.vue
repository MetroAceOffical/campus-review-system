<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {session} from '../../session'
import * as api from '../../api/training'
import RecordPagination from '../RecordPagination.vue'
import ExperimentChart from '../experiments/ExperimentChart.vue'
const emit=defineEmits<{open:[modelId:string]}>()
const route=useRoute(),router=useRouter(),items=ref<api.ModelBundle[]>([]),page=ref(1),pageSize=ref(12),total=ref(0),q=ref(''),error=ref(''),busy=ref(false)
let alive=true,timer:ReturnType<typeof setInterval>|undefined
const percent=(value?:number)=>value==null?'—':`${(value*100).toFixed(1)}%`
const states:Record<string,string>={QUEUED:'排队中',RUNNING:'训练中',COMPLETED:'六模型已完成',FAILED:'当前阶段失败',CANCELLED:'已取消',BLOCKED:'待补充样本'}
async function load(){if(busy.value)return;busy.value=true;try{const data=await api.bundles(page.value,pageSize.value,q.value);if(alive){items.value=data.items;total.value=data.total;error.value=''}}catch(e){error.value=e instanceof Error?e.message:'模型组读取失败'}finally{busy.value=false}}
function chart(bundle:api.ModelBundle){return {tooltip:{trigger:'axis'},legend:{},grid:{left:45,right:15,top:35,bottom:25},xAxis:{type:'category',data:bundle.state.models.map(m=>m.family.toUpperCase())},yAxis:{type:'value',min:0,max:1},series:['recall','f1','precision'].map((key,i)=>({name:['验证召回率','验证F1','验证精确率'][i],type:'bar',data:bundle.state.models.map(m=>(m as unknown as {validation?:Record<string,number>}).validation?.[key]??null)}))}}
async function continueBundle(bundle:api.ModelBundle){
 const member=bundle.state.models.find(m=>m.family==='bert');if(!member)return
 if(route.query.selectParent==='1'&&route.query.flow){emit('open',member.modelId);return}
 await router.push({path:'/training',query:{flow:'',dataset:bundle.datasetId,version:bundle.state.cleanVersionId,parentBundle:bundle.pipelineId,step:'0',tab:'new'}})
}
async function retry(id:string){try{await api.controlPipeline(id,'retry');await load()}catch(e){error.value=e instanceof Error?e.message:'重试失败'}}
onMounted(()=>{void load();timer=setInterval(()=>void load(),4000)})
onBeforeUnmount(()=>{alive=false;if(timer)clearInterval(timer)})
</script>
<template>
 <section class="work-panel"><div class="work-heading"><div><h2>六模型组</h2><span class="muted">一组数据 · 六种算法 · 共同划分</span></div><RouterLink v-if="session.user?.role==='ADMIN'" class="link-button" :to="{path:'/training',query:{flow:'',tab:'new'}}">新建训练组</RouterLink></div>
 <div class="work-search"><el-input v-model="q" placeholder="搜索模型组" aria-label="搜索模型组" @change="page=1;load()"/><el-button @click="load">搜索</el-button><RecordPagination v-model:current-page="page" v-model:page-size="pageSize" :total="total" @change="load"/></div>
 <p v-if="error" class="work-error" role="alert">{{error}}</p><el-empty v-if="!items.length&&!busy" description="选择正式数据集，开始六模型组训练"/>
 <article v-for="bundle in items" :key="bundle.pipelineId" class="bundle-record"><div class="work-heading"><h3>{{bundle.name}}</h3><el-tag :type="bundle.status==='COMPLETED'?'success':bundle.status==='FAILED'?'danger':'info'">{{states[bundle.status]||bundle.status}}</el-tag></div>
 <div class="bundle-counts"><strong>{{bundle.trainedCount}} / 6 <small>训练完成</small></strong><strong>{{bundle.evaluatedCount}} / 6 <small>独立评价</small></strong><span>组编号 {{bundle.pipelineId.slice(0,8)}}</span></div>
 <p v-if="bundle.error" class="work-error">{{bundle.error}}</p>
 <el-table :data="bundle.state.models" size="small"><el-table-column label="算法" width="130"><template #default="{row}">{{api.modelNames[row.family]}}</template></el-table-column><el-table-column prop="trainRows" label="训练样本"/><el-table-column label="验证召回率"><template #default="{row}">{{percent(row.validation?.recall)}}</template></el-table-column><el-table-column label="验证 F1"><template #default="{row}">{{percent(row.validation?.f1)}}</template></el-table-column><el-table-column label="测试 F1"><template #default="{row}">{{percent(row.test?.f1)}}</template></el-table-column><el-table-column label="详情" width="100"><template #default="{row}"><el-button size="small" @click="emit('open',row.modelId)">参数与图表</el-button></template></el-table-column></el-table>
 <details v-if="bundle.trainedCount>1"><summary>六模型共同验证集比较</summary><ExperimentChart title="六模型验证指标" :option="chart(bundle) as any"/></details>
 <div class="work-actions"><RouterLink class="link-button" :to="{path:'/training',query:{flow:'',dataset:bundle.datasetId,version:bundle.state.cleanVersionId,bundle:bundle.pipelineId,tab:'tasks'}}">查看组进度</RouterLink><el-button v-if="session.user?.role==='ADMIN'&&bundle.status==='COMPLETED'" @click="continueBundle(bundle)">{{route.query.selectParent==='1'?'选择该组继续训练':'整组继续训练'}}</el-button><el-button v-if="session.user?.role==='ADMIN'&&['FAILED','CANCELLED'].includes(bundle.status)" @click="retry(bundle.pipelineId)">重试失败阶段</el-button></div>
 </article></section>
</template>
<style scoped>.bundle-record{border-top:1px solid var(--line);padding:14px 0}.bundle-counts{display:flex;align-items:center;gap:28px;padding:8px 0 12px}.bundle-counts strong{font-size:24px;color:var(--el-color-primary)}.bundle-counts small{font-size:12px;font-weight:400;color:var(--muted);margin-left:6px}.bundle-counts>span{font-size:12px;color:var(--muted)}@media(max-width:650px){.bundle-counts{gap:12px;flex-wrap:wrap}}</style>
