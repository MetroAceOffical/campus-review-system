<script setup lang="ts">
import {onMounted,ref,watch} from 'vue'
import {useRoute} from 'vue-router'
const route=useRoute()
import * as training from '../../api/training'
import {createBundleRelease} from '../../api/delivery'
import {organizations} from '../../api/workbench'
import RecordPagination from '../RecordPagination.vue'
const props=defineProps<{bundleId?:string}>(),emit=defineEmits<{registered:[id:string]}>()
const selected=ref(''),name=ref(''),organization=ref('0'),items=ref<training.ModelBundle[]>([]),departments=ref<Array<{organizationId:string;name:string}>>([]),page=ref(1),size=ref(12),total=ref(0),q=ref(''),error=ref(''),busy=ref(false),current=ref<training.ModelBundle>()
async function load(){try{const result=await training.bundles(page.value,size.value,q.value);items.value=result.items;total.value=result.total}catch(e){error.value=e instanceof Error?e.message:'模型组读取失败'}}
async function choose(){if(!selected.value)return;try{current.value=await training.bundle(selected.value);name.value=(current.value.name+' · 审核发布').slice(0,120);const first=current.value.state.models[0];if(first)organization.value=(await training.model(first.modelId)).organizationId;error.value=''}catch(e){error.value=e instanceof Error?e.message:'模型组读取失败'}}
async function submit(){if(!selected.value||!name.value.trim()){error.value='请选择模型组并填写版本名称';return}busy.value=true;error.value='';try{const result=await createBundleRelease(organization.value,selected.value,name.value);emit('registered',result.id)}catch(e){error.value=e instanceof Error?e.message:'登记失败'}finally{busy.value=false}}
watch(()=>props.bundleId,async id=>{if(id){selected.value=id;await choose()}},{immediate:true})
onMounted(async()=>{await load();departments.value=await organizations()})
</script>
<template><section class="panel"><div class="section-heading"><h2>登记六模型审核组</h2><span class="muted">共同验证比较 → 整组核验 → 发布</span></div><p v-if="error" class="work-error" role="alert">{{error}}</p><div class="work-search"><el-input v-model="q" placeholder="搜索训练组" aria-label="搜索发布训练组" @change="page=1;load()"/><RecordPagination v-model:current-page="page" v-model:page-size="size" :total="total" @change="load"/></div><el-form label-position="top"><div class="work-grid"><el-form-item label="完整训练组"><el-select v-model="selected" :disabled="!!route.query.flow&&!!bundleId" aria-label="完整训练组" @change="choose"><el-option v-for="item in items" :key="item.pipelineId" :value="item.pipelineId" :disabled="item.status!=='COMPLETED'||item.evaluatedCount!==6" :label="`${item.name} · ${item.evaluatedCount}/6 已评价`"/><el-option v-if="current&&!items.some(i=>i.pipelineId===selected)" :value="selected" :label="current.name" :disabled="current.status!=='COMPLETED'"/></el-select></el-form-item><el-form-item label="发布版本名称"><el-input v-model="name" maxlength="120"/></el-form-item><el-form-item label="使用范围"><el-select v-model="organization"><el-option value="0" label="校级默认"/><el-option v-for="department in departments" :key="department.organizationId" :value="department.organizationId" :label="department.name"/></el-select></el-form-item></div></el-form><p class="muted">依据共同验证集的 F1、召回和误报推荐主模型，六种模型均参与正文审核。</p><el-button type="primary" :loading="busy" :disabled="current?.status!=='COMPLETED'||current.evaluatedCount!==6" @click="submit">核验完整六模型组</el-button></section></template>
