<script setup lang="ts">
import { computed,ref,watch,onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import * as datasets from '../../api/workbench'
import * as training from '../../api/training'
import * as delivery from '../../api/delivery'
import { getFlow,updateFlow,type FlowContext } from '../../api/flows'
import { session } from '../../session'
import { workflowContext } from '../../workflow-context'
import { activeFlow } from '../../flow-session'
import { flowSteps,flowDestination } from '../../flow-navigation'
import { versionName } from '../../workbench-guidance'
import AppIcon from '../AppIcon.vue'
const route=useRoute(),error=ref(''),saving=ref(false)
const paths=['/datasets','/training','/models','/releases','/reference-imports','/references']
const visible=computed(()=>paths.includes(route.path)&&session.user?.role!=='MEMBER'&&!!route.query.flow)
let working=false,pending=false,alive=true,owner=''
async function sync(){
  const path=route.fullPath,user=session.user?.userId||'',valid=()=>alive&&route.fullPath===path&&session.user?.userId===user
  if(owner!==user){activeFlow.value=undefined;workflowContext.dataset=undefined;workflowContext.version='';workflowContext.run=undefined;workflowContext.model=undefined;owner=user}
  if(!paths.includes(route.path)||!user||session.user?.role==='MEMBER'){activeFlow.value=undefined;return}
  error.value=''
  try{
    const id=String(route.query.flow||''),flow=id?await getFlow(id):undefined
    if(!valid())return
    if(!id)activeFlow.value=undefined
    let context:FlowContext={...flow?.context},dataset=String(route.query.dataset||context.datasetId||''),version=String(route.query.version||context.versionId||'')
    if(flow?.kind==='CONTINUE' && !context.parentModelId && route.query.selectParent){dataset=context.datasetId||'';version=context.versionId||''}
    if(flow&& !route.query.selectParent && ((route.query.dataset&&dataset!==context.datasetId)||(route.query.version&&version!==context.versionId)))context={...(context.parentModelId?{parentModelId:context.parentModelId}:{}),datasetId:dataset,versionId:version}
    const bundleId=String(route.query.bundle||route.query.bundleId||context.bundleId||'')
    const bundle=bundleId?await training.bundle(bundleId):undefined
    workflowContext.bundle=bundle
    if(bundle){context.bundleId=bundle.pipelineId;dataset=bundle.datasetId;version=bundle.state.cleanVersionId||version;context.datasetId=dataset;context.versionId=version;if(bundle.state.preparationId)context.preparationId=bundle.state.preparationId;const canonical=bundle.state.models.find(m=>m.family==='bert');if(canonical){context.trainingRunId=canonical.modelId;context.modelId=canonical.modelId;if(canonical.evaluationRunId)context.evaluationRunId=canonical.evaluationRunId}else{delete context.trainingRunId;delete context.modelId;delete context.evaluationRunId}}
    let run:training.ComputeRun|undefined
    if(route.path==='/training'&&route.query.run){
      run=await training.run(String(route.query.run));dataset=run.datasetId;version=run.inputVersionId
      context.datasetId=dataset;context.versionId=version
      if(bundle){if(!bundle.state.steps.some(s=>s.runId===run!.runId))throw new Error('该运行不属于当前模型组')}
      else if(run.action==='TRAIN'){
        if(flow&&(flow.kind==='CONTINUE'?(run.options.parentModelId||'')!==(context.parentModelId||''):!!run.options.parentModelId))throw new Error('该训练使用了不同起始模型，请从任务首页单独打开')
        if(context.trainingRunId!==run.runId){delete context.modelId;delete context.evaluationRunId;delete context.releaseId}context.trainingRunId=run.runId;if(run.status==='COMPLETED')context.modelId=run.runId;if(run.options.preparationId)context.preparationId=run.options.preparationId
      }
      else if(['PREPARE','GENERATE'].includes(run.action)){if(context.preparationId!==run.runId){delete context.trainingRunId;delete context.modelId;delete context.evaluationRunId;delete context.releaseId}context.preparationId=run.runId}
      else if(run.action==='EVALUATE'){if(flow&&context.modelId!==run.options.modelId)throw new Error('该评价不属于当前任务模型');if(context.evaluationRunId!==run.runId)delete context.releaseId;context.evaluationRunId=run.runId;context.modelId=run.options.modelId}
    }
    if(route.path==='/models'&&route.query.model&&!route.query.selectParent){
      const model=await training.model(String(route.query.model));dataset=model.datasetId;version=model.inputVersionId||(await training.run(model.runId)).inputVersionId
      if(!flow||context.trainingRunId===model.runId){context.datasetId=dataset;context.versionId=version;context.modelId=model.modelId;context.trainingRunId=model.runId}
    }
    if(route.query.preparation){const preparation=String(route.query.preparation);if(run?.action==='TRAIN'&&run.options.preparationId!==preparation)throw new Error('该训练与所选样本划分不一致');if(context.preparationId!==preparation){delete context.trainingRunId;delete context.modelId;delete context.evaluationRunId;delete context.releaseId}context.preparationId=preparation}
    if(route.path==='/reference-imports'&&route.query.batch)context.importId=String(route.query.batch)
    if(flow&&!dataset){workflowContext.dataset=undefined;workflowContext.version='';workflowContext.run=undefined;workflowContext.model=undefined}
    if(dataset){
      const data=await datasets.dataset(dataset)
      if(!valid())return
      if(!version)version=data.versions[0]?.versionId||''
      context.datasetId=dataset;if(version)context.versionId=version
      const bound=[context.preparationId,context.trainingRunId,context.evaluationRunId].filter((id):id is string=>!!id&&!data.runs.some(r=>r.runId===id))
      const missing=await Promise.all(bound.map(id=>training.run(id)));if(!valid())return
      data.runs.push(...missing as unknown as datasets.Run[])
      if(context.releaseId){const release=await delivery.release(context.releaseId);if(!valid())return;data.modelReleases=[...(data.modelReleases||[]).filter(r=>r.id!==release.id),{id:release.id,versionId:context.versionId||'',status:release.status,active:release.active}]}
      workflowContext.dataset=data;workflowContext.version=version
      if(flow){workflowContext.run=context.trainingRunId;workflowContext.model=context.modelId}
      if(run?.action==='TRAIN'){workflowContext.run=run.runId;workflowContext.model=run.status==='COMPLETED'?run.runId:undefined}
      if(context.modelId){workflowContext.model=context.modelId;workflowContext.run=context.trainingRunId}
    }
    if(flow&&valid()){
      const step=String(route.query.flowStep||({'/datasets':context.datasetId?'quality':'data','/training':run?(['PREPARE','GENERATE'].includes(run.action)?'prepare':'train'):route.query.step==='1'?'prepare':route.query.step==='2'?'train':'data','/models':route.query.selectParent?'parent':route.query.tab==='prediction'?'predict':'evaluate','/reference-imports':'library','/releases':'predict'} as Record<string,string>)[route.path]||flow.currentStep||'data')
      if(JSON.stringify(context)!==JSON.stringify(flow.context)||step!==flow.currentStep){saving.value=true;const updated=await updateFlow(flow,context,step);if(valid())activeFlow.value=updated}
      else activeFlow.value=flow
    }
  }catch(e){if(valid()){error.value=e instanceof Error?e.message:'读取任务失败';activeFlow.value=undefined;workflowContext.dataset=undefined;workflowContext.version='';workflowContext.model=undefined;workflowContext.run=undefined}}finally{saving.value=false}
}
async function schedule(){pending=true;if(working)return;working=true;try{while(pending&&alive){pending=false;await sync()}}finally{working=false}}
watch(()=>[route.fullPath,session.user?.userId,workflowContext.bundle?.status,workflowContext.bundle?.trainedCount,workflowContext.bundle?.evaluatedCount,workflowContext.dataset?.runs.map(r=>r.runId+':'+r.status).join('|')],()=>void schedule(),{immediate:true})
onBeforeUnmount(()=>{alive=false})
const steps=computed(()=>activeFlow.value?flowSteps(activeFlow.value,workflowContext.dataset,workflowContext.bundle).filter(s=>session.user?.role==='ADMIN'||!['parent','prepare','train'].includes(s.key)):[])
const current=computed(()=>String(route.query.flowStep||activeFlow.value?.currentStep||''))
const version=computed(()=>workflowContext.dataset?.versions.find(v=>v.versionId===workflowContext.version))
</script>
<template>
  <section v-if="visible" class="task-flow" aria-label="当前任务流程">
    <div class="flow-heading"><div><AppIcon name="data" :size="17"/><strong>{{activeFlow?.name||'读取任务'}}</strong><span v-if="workflowContext.dataset">{{workflowContext.dataset.name}}</span><small v-if="version" :title="versionName(version)">{{version.stage==='CLEAN'?'清洗':'原始'}} · {{version.rowCount??'—'}}条</small></div><span v-if="saving" class="muted">保存中</span><RouterLink v-else class="link-button" to="/home">任务首页</RouterLink></div>
    <p v-if="error" class="work-error" role="alert">{{error}} <el-button size="small" @click="schedule">重新读取</el-button></p>
    <ol v-if="activeFlow" class="flow-steps"><li v-for="(step,index) in steps" :key="step.key" :class="[step.status,{current:current===step.key}]"><RouterLink v-if="step.enabled" :to="{...flowDestination(activeFlow,step.key),query:{...flowDestination(activeFlow,step.key).query,flowStep:step.key}}" :aria-current="current===step.key?'step':undefined"><span class="step-number"><AppIcon v-if="step.status==='done'" name="check" :size="14"/><template v-else>{{index+1}}</template></span><span>{{step.label}}</span><small>{{({done:'已完成',active:'进行中',waiting:'待进行',error:'需处理'})[step.status]}}</small></RouterLink><span v-else class="disabled-step"><span class="step-number">{{index+1}}</span>{{step.label}}</span></li></ol>
  </section>
</template>
<style scoped>.task-flow{position:sticky;top:var(--header-height);z-index:35;background:var(--canvas);border:1px solid var(--line);border-top:3px solid var(--el-color-primary);padding:10px 14px;margin-bottom:14px;box-shadow:0 3px 8px #142a4708}.flow-heading{display:flex;justify-content:space-between;gap:12px;align-items:center}.flow-heading>div{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.flow-heading strong{font-size:14px}.flow-heading span,.flow-heading small{font-size:11px;color:var(--muted)}.flow-steps{display:flex;margin:10px 0 0;padding:0;list-style:none;gap:8px;overflow-x:auto}.flow-steps li{flex:1;min-width:116px}.flow-steps a,.disabled-step{display:flex;align-items:center;gap:6px;border:1px solid var(--line);padding:8px;color:var(--heading);text-decoration:none;white-space:nowrap;font-size:12px}.flow-steps small{font-size:10px;margin-left:auto;color:var(--muted)}.step-number{width:20px;height:20px;display:inline-grid;place-items:center;background:var(--soft);font-size:11px;flex-shrink:0}.done .step-number{color:var(--el-color-success)}.error a{border-color:var(--el-color-danger)}.current a{background:var(--soft);border-color:var(--el-color-primary);color:var(--el-color-primary);font-weight:600}.disabled-step{color:var(--muted);opacity:.7}@media(max-width:800px){.task-flow{top:var(--header-height);padding:8px}.flow-heading small{display:none}}</style>
