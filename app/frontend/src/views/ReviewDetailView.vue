<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {ElMessageBox} from 'element-plus'
import ReadOnlyDocument from '../components/ReadOnlyDocument.vue'
import TextReviewWorkspace from '../components/TextReviewWorkspace.vue'
import TextEvidence from '../components/TextEvidence.vue'
import ImageEvidence from '../components/ImageEvidence.vue'
import OcrEvidence from '../components/OcrEvidence.vue'
import DocumentChecks from '../components/DocumentChecks.vue'
import RecordPagination from '../components/RecordPagination.vue'
import {getSubmission,getSubmissions,stateLabel,decisionLabel,type Snapshot,type Version} from '../api/manuscripts'
import {getFormalReport,decide,retryItem,textEvidence,imageEvidence,qualityText,type Report,type ReportItem} from '../api/review'
import * as checks from '../api/checks'
import type {Check} from '../api/checks'
import {codePointRangeToEditorRange,type EditorRange} from '../editor/positions'
import type {DocumentNode} from '../types/document'
const route=useRoute(),router=useRouter(),versions=ref<Version[]>([]),selected=ref(''),snapshot=ref<Snapshot>(),report=ref<Report>(),loading=ref(false),error=ref(''),activeTab=ref('TEXT'),selectedImage=ref(''),decision=ref('APPROVE'),reason=ref(''),deciding=ref(false),rechecking=ref(false),retrying=ref<string[]>([]),highlights=ref<EditorRange[]>([]),article=ref<HTMLElement>()
const selectedCheck=ref(''),currentCheck=ref<Check>(),checkRows=ref<Check[]>([]),checkPage=ref(1),checkSize=ref(10),checkTotal=ref(0)
const images=computed(()=>{const result:Array<{nodeId:string;fileId:string;caption:string;number:number}>=[];function walk(n:DocumentNode){if(n.type==='campusImage')result.push({nodeId:String(n.attrs?.nodeId),fileId:String(n.attrs?.fileId),caption:String(n.attrs?.caption??''),number:result.length+1});n.content?.forEach(walk)}if(snapshot.value)walk(snapshot.value.content);return result})
const image=computed(()=>images.value.find(i=>i.nodeId===selectedImage.value))
const item=computed(()=>report.value?.items.find(i=>i.type===activeTab.value&&(i.type==='TEXT'||i.targetKey===selectedImage.value)))
const textItem=computed(()=>report.value?.items.find(i=>i.type==='TEXT'))
const contentEvidence=computed(()=>selectedCheck.value?currentCheck.value?.result?.evidence||[]:textEvidence(textItem.value?.evidence||[]))
const contentStatus=computed(()=>selectedCheck.value?currentCheck.value?.status:textItem.value?.status)
const configuration=computed(()=>selectedCheck.value?currentCheck.value?.contentProfile?.textConfig.configId:String((report.value?.pipelineManifest?.textConfig as {configId?:string})?.configId||''))
const library=computed(()=>selectedCheck.value?currentCheck.value?.contentProfile?.libraryGenerationId:report.value?.libraryGenerationId)
const rerunImages=computed(()=>currentCheck.value?.result?.imageResults?.find(i=>i.nodeId===selectedImage.value))
const controlsBusy=computed(()=>deciding.value||rechecking.value||loading.value)
let timer:ReturnType<typeof setTimeout>|undefined,checkTimer:ReturnType<typeof setTimeout>|undefined,active=true,selection=0,checkSelection=0,historyTicket=0,loadTicket=0,decisionSignature='',decisionKey=''
const retryKeys=new Map<string,string>()
const checkLabel=(c:Check)=>`${c.createdAt?new Date(c.createdAt).toLocaleString('zh-CN'):'复检'} · ${stateLabel[c.status]||c.status}${c.contentProfile?.textConfig.webBert?' · 网页BERT':''}`
function stop(){if(timer)clearTimeout(timer);if(checkTimer)clearTimeout(checkTimer)}
async function refresh(current=selection){
  if(timer)clearTimeout(timer);const version=versions.value.find(v=>v.submissionId===selected.value);if(!version?.batchId)return
  try{const result=await getFormalReport(version.batchId);if(!active||current!==selection)return;report.value=result;if(['QUEUED','RUNNING','WAITING_SERVICE'].includes(result.status))timer=setTimeout(()=>void refresh(current),3000)}catch(e){if(active&&current===selection)error.value=e instanceof Error?e.message:'报告读取失败'}
}
async function readHistory(){
  const token=selection,request=++historyTicket,version=selected.value;if(!snapshot.value)return
  try{const result=await checks.history(snapshot.value.manuscriptId,version,checkPage.value,checkSize.value,'content');if(active&&token===selection&&request===historyTicket){checkRows.value=result.items;checkTotal.value=result.total}}catch(e){if(token===selection&&request===historyTicket)error.value=e instanceof Error?e.message:'复检历史读取失败'}
}
async function refreshCheck(token=checkSelection,version=selection){
  if(checkTimer)clearTimeout(checkTimer);const id=selectedCheck.value;if(!id)return
  try{const result=await checks.get(id);if(!active||token!==checkSelection||version!==selection)return;if(result.submissionId!==selected.value||result.kind!=='CONTENT')throw new Error('该复检记录不属于当前送审版本');currentCheck.value=result;if(!checks.done(result.status))checkTimer=setTimeout(()=>void refreshCheck(token,version),1500);else await readHistory()}catch(e){if(active&&token===checkSelection&&version===selection)error.value=e instanceof Error?e.message:'复检读取失败'}
}
async function selectReport(){
  const token=++checkSelection;currentCheck.value=undefined;if(checkTimer)clearTimeout(checkTimer)
  await router.replace({query:{...route.query,check:selectedCheck.value||undefined}})
  if(selectedCheck.value)await refreshCheck(token)
}
async function select(){
  stop();const token=++selection;++checkSelection;loading.value=true;report.value=undefined;snapshot.value=undefined;currentCheck.value=undefined;checkRows.value=[];checkPage.value=1;checkTotal.value=0;highlights.value=[];error.value='';reason.value='';decision.value='APPROVE'
  try{if(route.query.submission!==selected.value)await router.replace({query:{...route.query,submission:selected.value,check:undefined}});const value=await getSubmission(selected.value);if(!active||token!==selection)return;snapshot.value=value;selectedImage.value=images.value[0]?.nodeId||'';selectedCheck.value=String(route.query.check||'');await Promise.all([refresh(token),readHistory()]);if(selectedCheck.value)await refreshCheck(checkSelection,token)}catch(e){if(token===selection)error.value=e instanceof Error?e.message:'版本读取失败'}finally{if(token===selection)loading.value=false}
}
async function load(){const token=++loadTicket;stop();selection++;snapshot.value=undefined;loading.value=true;try{const first=await getSubmission(String(route.params.id)),history=await getSubmissions(first.manuscriptId);if(!active||token!==loadTicket)return;versions.value=history.items;selected.value=history.items.find(v=>v.submissionId===route.query.submission)?.submissionId||first.submissionId;await select()}catch(e){if(active&&token===loadTicket){loading.value=false;error.value=e instanceof Error?e.message:'读取失败'}}}
async function recheck(){
  if(!snapshot.value||controlsBusy.value)return;rechecking.value=true;error.value='';const version=selected.value,token=selection
  try{const result=await checks.start(snapshot.value.manuscriptId,version,'CONTENT',snapshot.value);if(!active||token!==selection)return;selectedCheck.value=result.checkId;currentCheck.value=result;await selectReport();await readHistory();activeTab.value='TEXT'}catch(e){if(token===selection)error.value=e instanceof Error?e.message:'复检未开始'}finally{rechecking.value=false}
}
async function locate(start:number,end:number){if(!snapshot.value?.positionMap)return;try{highlights.value=codePointRangeToEditorRange(snapshot.value.content,snapshot.value.positionMap,start,end);await nextTick();const target=Array.from(article.value?.querySelectorAll<HTMLElement>('[data-node-id]')||[]).find(e=>e.dataset.nodeId===highlights.value[0]?.nodeId);target?.scrollIntoView({block:'center',behavior:'smooth'})}catch(e){error.value=e instanceof Error?e.message:'定位失败'}}
async function retry(entry:ReportItem){if(!entry.activeAttemptId||retrying.value.includes(entry.itemId))return;const signature=`${entry.itemId}:${entry.activeAttemptId}`;if(!retryKeys.has(signature))retryKeys.set(signature,crypto.randomUUID());retrying.value.push(entry.itemId);try{await retryItem(entry.itemId,retryKeys.get(signature)!,entry.activeAttemptId);await refresh()}catch(e){error.value=e instanceof Error?e.message:'重试失败'}finally{retrying.value=retrying.value.filter(id=>id!==entry.itemId)}}
async function submitDecision(){
  if(controlsBusy.value||!snapshot.value||selectedCheck.value&&currentCheck.value?.status!=='COMPLETED')return
  if(decision.value!=='APPROVE'&&!reason.value.trim()){error.value='退回或拒绝必须填写理由';return}
  const version=selected.value,token=selection,checkId=selectedCheck.value||undefined;deciding.value=true
  try{
    try{await ElMessageBox.confirm(`确认对第${snapshot.value.versionNo}版作出“${decisionLabel[decision.value]}”决定？`,'人工审核决定',{confirmButtonText:'确认决定',cancelButtonText:'继续审核'})}catch{return}
    if(!active||token!==selection)return
    const signature=JSON.stringify({version,decision:decision.value,reason:reason.value,checkId});if(signature!==decisionSignature){decisionSignature=signature;decisionKey=crypto.randomUUID()}
    await decide(version,decisionKey,decision.value,reason.value,checkId);const value=await getSubmission(version);if(active&&token===selection){snapshot.value=value;await refresh()}
  }catch(e){if(active&&token===selection)error.value=e instanceof Error?e.message:'决定未确认，请重试同次操作'}finally{deciding.value=false}
}
watch(()=>route.params.id,()=>void load(),{immediate:true})
watch(()=>[route.query.submission,route.query.check],()=>{if(!snapshot.value)return;const version=String(route.query.submission||selected.value),check=String(route.query.check||'');if(version!==selected.value){selected.value=version;void select()}else if(check!==selectedCheck.value){selectedCheck.value=check;currentCheck.value=undefined;if(checkTimer)clearTimeout(checkTimer);checkSelection++;if(check)void refreshCheck(checkSelection)}})
onBeforeUnmount(()=>{active=false;selection++;checkSelection++;loadTicket++;stop()})
</script>
<template>
  <el-alert v-if="error" :title="error" type="error" :closable="false"/>
  <div class="review-controls panel">
    <el-button :disabled="deciding" @click="router.push('/reviews')">返回审核列表</el-button>
    <el-select v-model="selected" aria-label="审核版本" :disabled="controlsBusy" @change="select"><el-option v-for="v in versions" :key="v.submissionId" :value="v.submissionId" :label="`第${v.versionNo}版 · ${new Date(v.submittedAt).toLocaleString('zh-CN')}`"/></el-select>
    <el-select v-model="selectedCheck" aria-label="检测记录" :disabled="controlsBusy" @change="selectReport"><el-option value="" label="原送审检测"/><el-option v-if="currentCheck&&!checkRows.some(c=>c.checkId===currentCheck!.checkId)" :value="currentCheck.checkId" :label="checkLabel(currentCheck)"/><el-option v-for="c in checkRows" :key="c.checkId" :value="c.checkId" :label="checkLabel(c)"/></el-select>
    <el-button type="primary" :loading="rechecking" :disabled="controlsBusy" @click="recheck">按当前配置重新检测</el-button>
    <details v-if="checkTotal" class="check-history-pages"><summary>复检记录 · {{checkTotal}}条</summary><RecordPagination v-model:current-page="checkPage" v-model:page-size="checkSize" :total="checkTotal" @change="readHistory"/></details>
  </div>
  <div v-loading="loading"><template v-if="snapshot">
    <div class="review-context"><strong>第{{snapshot.versionNo}}版 · {{snapshot.title}}</strong><span>{{selectedCheck?'当前查看复检记录':'当前查看原送审记录'}} · {{stateLabel[contentStatus||'']||contentStatus||'待检测'}}</span><small v-if="configuration">配置{{configuration.slice(0,18)}} · 参考库{{library}}</small></div>
    <el-tabs v-model="activeTab" class="review-tabs"><el-tab-pane label="正文全文对照" name="TEXT"/><el-tab-pane label="图片复用" name="IMAGE"/><el-tab-pane label="OCR文字" name="OCR_AND_TEXT"/><el-tab-pane label="语法检查" name="GRAMMAR"/><el-tab-pane label="图文一致性" name="IMAGE_TEXT"/></el-tabs>
    <template v-if="activeTab==='TEXT'">
      <TextReviewWorkspace v-if="contentStatus==='COMPLETED'" :document="snapshot" :position-map="snapshot.positionMap" :evidence="contentEvidence" :batch="selectedCheck?undefined:report?.batchId" :check="selectedCheck||undefined"/>
      <section v-else class="panel"><p>{{stateLabel[contentStatus||'']||contentStatus||'等待检测'}}<template v-if="currentCheck?.error"> · {{currentCheck.error}}</template></p><el-button v-if="!selectedCheck&&textItem&&['FAILED','INTERRUPTED'].includes(textItem.status)" :loading="retrying.includes(textItem.itemId)" @click="retry(textItem)">重试失败项</el-button><ReadOnlyDocument :document="snapshot"/></section>
    </template>
    <div v-else class="review-other-columns">
      <section ref="article" class="panel review-document"><ReadOnlyDocument :document="snapshot" :highlights="highlights"/></section>
      <section class="panel review-evidence">
        <DocumentChecks v-if="['GRAMMAR','IMAGE_TEXT'].includes(activeTab)" :key="activeTab" :manuscript-id="snapshot.manuscriptId" :submission-id="snapshot.submissionId" :document="snapshot" :panel="activeTab==='GRAMMAR'?'grammar':'image'" readonly @locate="locate"/>
        <template v-else>
          <el-select v-if="images.length" v-model="selectedImage" aria-label="证据配图"><el-option v-for="entry in images" :key="entry.nodeId" :value="entry.nodeId" :label="`配图${entry.number}${entry.caption?' · '+entry.caption:''}`"/></el-select><el-empty v-else description="本版没有配图"/>
          <template v-if="activeTab==='IMAGE' &amp;&amp; selectedCheck"><ImageEvidence v-if="image &amp;&amp; contentStatus==='COMPLETED'" :evidence="rerunImages?.evidence||[]" :query-file-id="image.fileId" :image-number="image.number"/><p v-else>{{stateLabel[contentStatus||'']||contentStatus||'等待读取复检'}}<template v-if="currentCheck?.error"> · {{currentCheck.error}}</template></p></template>
          <template v-else-if="item">
            <div class="section-heading"><span>{{stateLabel[item.status]}}<template v-if="activeTab==='OCR_AND_TEXT'"> · 送审OCR记录</template></span><el-button v-if="['FAILED','INTERRUPTED'].includes(item.status)" size="small" :loading="retrying.includes(item.itemId)" @click="retry(item)">重试失败项</el-button></div>
            <el-alert v-if="item.activeAttempt?.errorCode" :title="`${item.activeAttempt.errorCode}：${item.activeAttempt.errorMessage}`" type="error" :closable="false"/>
            <ImageEvidence v-if="activeTab==='IMAGE'&&image&&item.status==='COMPLETED'" :evidence="imageEvidence(item.evidence)" :query-file-id="image.fileId" :image-number="image.number"/>
            <template v-if="activeTab==='OCR_AND_TEXT'&&image&&item.activeAttempt?.result.ocrStatus"><OcrEvidence :result="item.activeAttempt.result" :file-id="image.fileId" :image-number="image.number"/><TextEvidence v-if="item.activeAttempt.result.textSearchStatus==='COMPLETED'" :evidence="item.activeAttempt.result.textEvidence||[]"/></template>
            <p v-if="qualityText(item.qualityFlags||[])" class="muted">{{qualityText(item.qualityFlags||[])}}</p><p v-if="['QUEUED','RUNNING'].includes(item.status)">处理完成后自动更新</p><p v-if="item.status==='NOT_APPLICABLE'">本项没有适用内容</p>
          </template>
        </template>
      </section>
    </div>
    <section id="review-decision" class="panel decision-panel">
      <template v-if="snapshot.decision"><h2>人工决定：{{decisionLabel[snapshot.decision.decision]}}</h2><p>{{snapshot.decision.reason||'无补充理由'}} · {{new Date(snapshot.decision.decidedAt).toLocaleString('zh-CN')}}</p></template>
      <template v-else-if="snapshot.lifecycleStatus==='PENDING'"><h2>人工审核决定</h2><div class="decision-actions"><el-radio-group v-model="decision" :disabled="deciding"><el-radio-button value="APPROVE">通过</el-radio-button><el-radio-button value="RETURN">退回</el-radio-button><el-radio-button value="REJECT">拒绝</el-radio-button></el-radio-group><el-button type="primary" :loading="deciding" :disabled="controlsBusy||!!selectedCheck&&currentCheck?.status!=='COMPLETED'" @click="submitDecision">提交人工决定</el-button></div><el-input v-model="reason" :disabled="deciding" type="textarea" :rows="2" maxlength="4000" aria-label="审核理由" :placeholder="decision==='APPROVE'?'补充说明（可选）':'填写退回或拒绝理由'"/></template>
    </section>
    <details class="panel review-provenance"><summary>本次检测配置</summary><pre>{{JSON.stringify(selectedCheck?currentCheck?.contentProfile:report?.pipelineManifest,null,2)}}</pre></details>
  </template></div>
</template>
<style scoped>
.review-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:12px 14px}.review-controls>.el-select{width:245px}.check-history-pages{margin-left:auto;font-size:12px}.check-history-pages summary{cursor:pointer}.review-context{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:12px;margin:10px 0}.review-context>strong{font-size:14px}.review-context>span,.review-context>small{color:var(--muted)}.review-other-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:12px}.review-other-columns>.panel{padding:16px;min-width:0}.review-document{max-height:75vh;overflow:auto;align-self:start}.review-evidence>.el-select{margin-bottom:12px;width:100%}.decision-panel{margin-top:14px;padding:14px 16px}.decision-panel h2{font-size:15px;margin:0 0 10px}.decision-actions{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.decision-panel p{font-size:13px;margin:0}.review-provenance{padding:12px 16px;font-size:12px}.review-provenance summary{cursor:pointer}.review-provenance pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;font-size:11px}@media(max-width:900px){.review-other-columns{grid-template-columns:1fr}.review-controls>.el-select{width:100%}.check-history-pages{margin-left:0}}
</style>
