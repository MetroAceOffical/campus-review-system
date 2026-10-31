<script setup lang="ts">
import type { TextEvidenceItem } from '../api/review'
import { computed, ref } from 'vue'
import OcrEvidence from './OcrEvidence.vue'
const props = defineProps<{ item: TextEvidenceItem; allowLocate?: boolean }>()
defineEmits<{ locate: [start: number, end: number] }>()
const expandedSources = ref<string[]>([])
const citationLabels: Record<string,string> = { CITED:'已标注引用',SOURCE_MISMATCH:'来源不一致',UNCITED:'未标注来源',EXTERNAL_REVIEW:'站外来源待核验' }
const citationStates = (item: TextEvidenceItem, start: number, end: number) => Array.from(new Set((item.citationChecks ?? []).filter(c=>c.queryStart<end&&c.queryEnd>start).map(c=>c.status)))

const semantic = computed(() => !!props.item.semanticSummary?.suspectedReuse)
const showAll = ref(false)
const expandedSemantic = ref(semantic.value ? ['semantic'] : [])
const literal = computed(() => props.item.literalAcceptedCandidate ?? (props.item.acceptedCandidate && props.item.literalSummary.matched_characters > 0))
const visibleWindows = computed(() => {
  const windows = [...props.item.semanticWindows].sort((a,b) => Number(!!b.citationSupport) - Number(!!a.citationSupport) || b.score - a.score)
  return showAll.value ? windows : windows.slice(0,6)
})
</script>
<template>
  <section class="evidence-card">
    <div class="section-heading">
      <strong>{{ item.sourceTitle }}</strong>
      <el-tag :type="item.fullyCited ? 'success' : semantic || literal ? 'warning' : 'info'" effect="plain">{{ item.fullyCited ? '已标注引用' : semantic ? '疑似语义复用' : literal ? '发现字面复用' : '相近来源' }}</el-tag>
    </div>

    <a class="source-external" v-if="item.sourceUrl" :href="item.sourceUrl" target="_blank" rel="noopener noreferrer">查看原始来源 ↗</a>
    <p v-else-if="item.sourceMetadata?.description">{{ item.sourceMetadata.description }}</p>
    <div v-if="semantic && (item.semanticSummary!.supportingPairs > 0 || item.semanticSummary!.matchedQueryCharacters > 0)" class="evidence-metrics semantic-metrics"><div v-if="item.semanticSummary!.supportingPairs > 0"><span>语义对应片段</span><strong>{{ item.semanticSummary!.supportingPairs }}<small> 组</small></strong></div><div v-if="item.semanticSummary!.matchedQueryCharacters > 0"><span>涉及本稿文字</span><strong>{{ item.semanticSummary!.matchedQueryCharacters }}<small> 字</small></strong></div><div v-if="item.semanticSummary?.queryCoverage !== undefined"><span>本稿语义覆盖</span><strong>{{ (item.semanticSummary.queryCoverage * 100).toFixed(1) }}%</strong></div></div>
    <p v-if="!semantic && item.literalSummary.matched_characters > 0" class="literal-evidence-summary">字面对应 <strong>{{item.literalSummary.matched_characters}}字</strong><template v-if="item.literalSummary.query_character_coverage > 0"> · 覆盖本稿 {{(item.literalSummary.query_character_coverage*100).toFixed(1)}}%</template><template v-if="item.literalSummary.longest_match > 0"> · 最长片段 {{item.literalSummary.longest_match}}字</template></p>
    <p v-if="semantic" :class="{ unsaved: !item.fullyCited }">{{ item.fullyCited ? '对应片段已标注站内引用。' : '发现多处语义相近片段，请结合下面的原文对照核对来源。' }}</p>
    <details class="literal-details"><summary>字面重复指标</summary><p class="muted">重复字符 {{item.literalSummary.matched_characters}} · 本稿覆盖 {{(item.literalSummary.query_character_coverage*100).toFixed(1)}}% · 最长片段 {{item.literalSummary.longest_match}}字</p></details>
    <div v-for="(match, index) in item.matches" :key="`${item.evidenceId}-${index}`" class="match-block">
      <el-tag v-for="status in citationStates(item,match.queryStart,match.queryEnd)" :key="status" :type="status==='CITED'?'success':'info'" size="small">{{citationLabels[status]}}</el-tag>
      <div class="match-pair"><div><span class="muted">本稿片段</span><p><mark>{{ match.queryText }}</mark></p></div><div><span class="muted">来源片段</span><p><mark>{{ match.sourceText }}</mark></p></div></div>
      <el-button v-if="allowLocate" size="small" @click="$emit('locate', match.queryStart, match.queryEnd)">定位正文</el-button>
    </div>
    <el-collapse v-if="item.semanticWindows.length" v-model="expandedSemantic">
      <el-collapse-item name="semantic" :title="item.semanticSummary ? '句子对齐语义证据' : 'BERT部分窗口语义辅助'">
        <p v-if="item.semanticSummary" class="muted">优先展示支持判定的{{ visibleWindows.length }}组片段。</p>
        <div v-for="(window, index) in visibleWindows" :key="index" class="semantic-window">
          <el-tag v-for="status in citationStates(item,window.queryStart,window.queryEnd)" :key="status" :type="status==='CITED'?'success':'info'" size="small">{{citationLabels[status]}}</el-tag>
          <p>{{ window.scoreType === 'CONTENT_CORRESPONDENCE_SCORE' ? 'M3对应分数' : 'BERT分数' }} {{ window.score.toFixed(4) }}</p>
          <div class="match-pair"><p>{{ window.queryText }}</p><p>{{ window.sourceText }}</p></div>
          <el-button v-if="allowLocate" size="small" @click="$emit('locate', window.queryStart, window.queryEnd)">定位语义片段</el-button>
        </div><el-button v-if="item.semanticWindows.length > 6" size="small" @click="showAll = !showAll">{{ showAll ? '收起片段' : `查看全部${item.semanticWindows.length}组对齐片段` }}</el-button>
      </el-collapse-item>
    </el-collapse>
    <el-collapse v-if="item.sourceKind === 'IMAGE_OCR' && item.sourceMetadata?.ocr && item.sourceMetadata.sourceFileId" v-model="expandedSources">
      <el-collapse-item :name="item.evidenceId" title="来源图片与OCR区域"><OcrEvidence v-if="expandedSources.includes(item.evidenceId)" :result="item.sourceMetadata.ocr" :file-id="item.sourceMetadata.sourceFileId" source /></el-collapse-item>
    </el-collapse>
    <details><summary>技术信息与证据编号</summary>    <p class="muted">来源{{ item.sourceWorkId }} / 修订{{ item.sourceRevisionId }} · {{ item.sourceKind === 'IMAGE_OCR' ? '来源图片OCR文字' : '来源正文' }} · TF-IDF {{ item.tfidfScore.toFixed(4) }}</p><small class="muted evidence-id">证据 {{ item.evidenceId }}</small></details>
  </section>
</template>

<style scoped>.semantic-metrics{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}.semantic-metrics>div{border-left:3px solid var(--el-color-warning)}</style>
