<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,ref,watch} from 'vue'
import {evidenceSource,type EvidenceSource,type TextEvidenceItem} from '../api/review'
import type {DocumentInput} from '../types/document'
import {codePointRangeToEditorRange,documentPositionMap,plainText,type PositionMap} from '../editor/positions'
import {evidencePairs,highlightText,summarizeEvidence,type EvidencePair} from '../review-summary'
import ReadOnlyDocument from './ReadOnlyDocument.vue'
import OcrEvidence from './OcrEvidence.vue'
import RecordPagination from './RecordPagination.vue'
const props=defineProps<{document:DocumentInput;positionMap?:PositionMap[];evidence:TextEvidenceItem[];batch?:string;check?:string}>()
const selected=ref(''),source=ref<EvidenceSource>(),error=ref(''),loading=ref(false),activePair=ref<EvidencePair>(),page=ref(1),size=ref(5),left=ref<HTMLElement>(),right=ref<HTMLElement>(),workspace=ref<HTMLElement>()
let ticket=0,alive=true
const sources=computed(()=>[...props.evidence].sort((a,b)=>Number(b.fullyCited||b.acceptedCandidate||b.semanticSummary?.suspectedReuse)-Number(a.fullyCited||a.acceptedCandidate||a.semanticSummary?.suspectedReuse)))
const item=computed(()=>sources.value.find(s=>s.evidenceId===selected.value))
const summary=computed(()=>item.value?summarizeEvidence(item.value,Array.from(plainText(props.document.content)).length):undefined)
const warningSources=computed(()=>new Set(sources.value.filter(e=>summarizeEvidence(e,0).warning).map(e=>e.sourceWorkId)).size)
const pairs=computed(()=>item.value?evidencePairs(item.value):[])
const shownPairs=computed(()=>pairs.value.slice((page.value-1)*size.value,page.value*size.value))
const selectedRanges=computed(()=>activePair.value?[activePair.value]:pairs.value.filter(p=>p.supported))
const queryHighlights=computed(()=>selectedRanges.value.flatMap(row=>{try{return codePointRangeToEditorRange(props.document.content,props.positionMap||documentPositionMap(props.document.content),row.queryStart,row.queryEnd)}catch{return[]}}))
const sourceParts=computed(()=>highlightText(source.value?.plainText||'',selectedRanges.value.flatMap(row=>row.sourceStart!==undefined&&row.sourceEnd!==undefined?[{start:row.sourceStart,end:row.sourceEnd}]:[])))
const safeUrl=computed(()=>/^https?:\/\//.test(source.value?.url||'')?source.value?.url:undefined)
async function readSource(){
  const token=++ticket;source.value=undefined;error.value='';activePair.value=undefined;page.value=1
  if(!item.value)return
  loading.value=true
  try{const value=await evidenceSource(item.value.evidenceId,{...(props.batch?{batch:props.batch}:{}),...(props.check?{check:props.check}:{})});if(alive&&token===ticket)source.value=value}
  catch(e){if(alive&&token===ticket)error.value=e instanceof Error?e.message:'来源全文读取失败'}finally{if(token===ticket)loading.value=false}
}
watch(()=>[props.evidence.map(e=>e.evidenceId).join('|'),props.batch,props.check],()=>{if(!sources.value.some(e=>e.evidenceId===selected.value))selected.value=sources.value[0]?.evidenceId||'';else void readSource()},{immediate:true})
watch(selected,()=>void readSource(),{immediate:true})
async function locate(row:EvidencePair){activePair.value=row;await nextTick();for(const pane of [left.value,right.value]){const mark=pane?.querySelector<HTMLElement>('mark');if(pane&&mark)pane.scrollTo({top:pane.scrollTop+mark.getBoundingClientRect().top-pane.getBoundingClientRect().top-pane.clientHeight*.35,behavior:'smooth'})}workspace.value?.scrollIntoView({block:'start',behavior:'smooth'})}
function citation(row:EvidencePair){const states=item.value?.citationChecks?.filter(c=>c.queryStart<row.queryEnd&&c.queryEnd>row.queryStart).map(c=>c.status)||[];return [...new Set(states)].map(s=>({CITED:'已标注引用',SOURCE_MISMATCH:'引用来源不一致',EXTERNAL_REVIEW:'站外来源待核验',UNCITED:'未标注来源'}[s]||s)).join(' · ')}
onBeforeUnmount(()=>{alive=false;ticket++})
</script>
<template>
  <section ref="workspace" class="text-review-workspace" style="scroll-margin-top:calc(var(--header-height) + 12px)">
    <div class="evidence-verdict" :class="{warning:warningSources>0}">
      <div><strong>{{warningSources?'检出疑似复用':'未发现复用提示'}}</strong><span v-if="warningSources">{{warningSources}}个来源存在有效复用证据</span><span v-else-if="sources.some(s=>s.fullyCited)">对应片段已标注引用</span><span v-else>可查看相近来源及片段</span></div>
      <div v-if="summary?.metrics.length" class="verdict-metrics"><div v-for="metric in summary.metrics" :key="metric.label"><span>{{metric.label}}</span><strong>{{metric.value}}<small>{{metric.unit}}</small></strong></div></div>
    </div>
    <div v-if="sources.length" class="compare-toolbar">
      <label for="comparison-source">对比来源</label><el-select id="comparison-source" v-model="selected" aria-label="选择对比来源" filterable><el-option v-for="entry in sources" :key="entry.evidenceId" :value="entry.evidenceId" :label="entry.sourceTitle+' · 修订'+entry.sourceRevisionId+(entry.sourceKind==='IMAGE_OCR'?' · 图片OCR':'')+' · '+summarizeEvidence(entry,0).verdict"/></el-select>
      <el-tag :type="summary?.warning?'warning':item?.fullyCited?'success':'info'">{{summary?.verdict}}</el-tag><el-button v-if="activePair" size="small" @click="activePair=undefined">显示全部位置</el-button>
    </div>
    <div class="fulltext-columns">
      <section class="fulltext-pane"><header>送审 / 检查原文</header><div ref="left" class="document-scroll" tabindex="0" aria-label="本稿全文"><ReadOnlyDocument :document="document" :highlights="queryHighlights"/></div></section>
      <section class="fulltext-pane" v-loading="loading"><header><span>{{item?.sourceKind==='IMAGE_OCR'?'来源图片文字':'来源全文'}}<small v-if="source"> · 检测时版本</small></span><a v-if="safeUrl" class="link-button" :href="safeUrl" target="_blank" rel="noopener noreferrer">原始网址</a></header><div ref="right" class="document-scroll" tabindex="0" aria-label="来源全文"><p v-if="error" class="work-error" role="alert">{{error}} <el-button size="small" @click="readSource">重新读取</el-button></p><template v-if="source"><h2 class="source-title">{{source.title}}</h2><OcrEvidence v-if="item?.sourceKind==='IMAGE_OCR' &amp;&amp; item.sourceMetadata?.sourceFileId &amp;&amp; item.sourceMetadata.ocr" :result="item.sourceMetadata.ocr" :file-id="item.sourceMetadata.sourceFileId" source/><h3 v-if="item?.sourceKind==='IMAGE_OCR'">识别文字对照</h3><p class="source-fulltext"><template v-for="(part,index) in sourceParts" :key="index"><mark v-if="part.marked">{{part.text}}</mark><template v-else>{{part.text}}</template></template></p></template><el-empty v-else-if="!loading&&!error" :description="sources.length?'选择来源文章':'没有相近来源'"/></div></section>
    </div>
    <section v-if="pairs.length" class="pair-evidence"><div class="pair-heading"><h3>对应片段</h3><span>{{item?.sourceTitle}}</span></div>
      <el-table :data="shownPairs" size="small"><el-table-column label="证据" width="125"><template #default="{row}"><el-tag size="small" :type="summary?.warning?'warning':'info'">{{row.kind}}</el-tag><small v-if="row.score!==undefined" class="pair-score">得分 {{row.score.toFixed(3)}}</small></template></el-table-column><el-table-column label="本稿片段" min-width="220"><template #default="{row}"><p class="pair-text">{{row.queryText}}</p><small class="citation-state">{{citation(row)}}</small></template></el-table-column><el-table-column label="来源片段" min-width="220"><template #default="{row}"><p class="pair-text">{{row.sourceText}}</p></template></el-table-column><el-table-column label="定位" width="85"><template #default="{row}"><el-button size="small" @click="locate(row)">对照</el-button></template></el-table-column></el-table>
      <RecordPagination v-model:current-page="page" v-model:page-size="size" :total="pairs.length"/>
    </section>
    <details v-if="item" class="raw-evidence"><summary>证据参数</summary><p>字面重复 {{item.literalSummary.matched_characters}}字 · 字面覆盖 {{(item.literalSummary.query_character_coverage*100).toFixed(1)}}% · 最长字面片段 {{item.literalSummary.longest_match}}字 · 检索得分 {{item.tfidfScore.toFixed(4)}}</p><p>来源{{item.sourceWorkId}} · 修订{{item.sourceRevisionId}} · 证据{{item.evidenceId}}</p><details><summary>全部原始对齐参数</summary><pre>{{JSON.stringify(item.semanticWindows,null,2)}}</pre></details></details>
  </section>
</template>
<style scoped>
.evidence-verdict{display:flex;align-items:center;justify-content:space-between;gap:16px;border:1px solid var(--line);border-left:4px solid var(--el-color-success);padding:12px 16px;background:var(--canvas);margin-bottom:12px}.evidence-verdict.warning{border-left-color:var(--el-color-warning);background:color-mix(in srgb,var(--el-color-warning) 7%,var(--canvas))}.evidence-verdict>div>strong{font-size:20px;display:block}.warning>div>strong{color:var(--el-color-warning-dark-2)}.evidence-verdict>div>span{font-size:12px;color:var(--muted)}.verdict-metrics{display:flex;gap:22px}.verdict-metrics>div>span{font-size:11px;display:block}.verdict-metrics>div>strong{display:block;font-size:23px;line-height:1.35}.verdict-metrics small{font-size:12px;margin-left:3px;font-weight:400}.compare-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:10px}.compare-toolbar label{font-size:12px;white-space:nowrap}.compare-toolbar .el-select{width:min(520px,65%)}.fulltext-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}.fulltext-pane{border:1px solid var(--line);min-width:0;background:var(--canvas)}.fulltext-pane>header{height:39px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;background:var(--soft);font-size:13px;font-weight:600;border-bottom:1px solid var(--line)}.fulltext-pane header small{font-size:11px;font-weight:400;color:var(--muted)}.document-scroll{height:clamp(360px,55vh,640px);overflow:auto;padding:16px 22px;scroll-padding:24px}.document-scroll:focus-visible{outline:2px solid var(--el-color-primary);outline-offset:-2px}.source-fulltext{font-family:"SimSun","Songti SC",serif;white-space:pre-wrap;overflow-wrap:anywhere;font-size:15px;line-height:1.9}.source-title{text-align:center;font-size:20px;line-height:1.5;margin:0 0 16px}.document-scroll :deep(.article-title){font-size:20px;line-height:1.5;margin:0 0 16px}.document-scroll :deep(.article-body){font-size:15px;line-height:1.9}.document-scroll mark,.document-scroll :deep(mark){background:color-mix(in srgb,var(--el-color-warning) 32%,var(--canvas));color:var(--heading)}.pair-evidence{border:1px solid var(--line);padding:12px;margin-top:12px}.pair-heading{display:flex;align-items:center;gap:16px;margin-bottom:8px}.pair-heading h3{font-size:14px;margin:0}.pair-heading span{font-size:12px;color:var(--muted)}.pair-text{margin:0;font-size:12px;line-height:1.6;max-height:100px;overflow:auto;white-space:pre-wrap}.pair-score,.citation-state{display:block;font-size:11px;margin-top:4px;color:var(--muted)}.raw-evidence{padding:10px 12px;border:1px solid var(--line);margin-top:10px;font-size:11px;overflow-wrap:anywhere}.raw-evidence summary{cursor:pointer;font-size:12px}@media(max-width:1100px){.verdict-metrics{gap:12px}.verdict-metrics>div>strong{font-size:20px}}@media(max-width:800px){.evidence-verdict{align-items:flex-start;flex-direction:column}.fulltext-columns{grid-template-columns:1fr}.document-scroll{height:400px}}
</style>
