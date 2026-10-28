<script setup lang="ts">
import type { TextEvidenceItem } from '../api/review'
import { ref } from 'vue'
import OcrEvidence from './OcrEvidence.vue'
defineProps<{ evidence: TextEvidenceItem[]; allowLocate?: boolean }>()
defineEmits<{ locate: [start: number, end: number] }>()
const expandedSources = ref<string[]>([])
</script>
<template>
  <p class="muted">查看来源片段，点击定位可在正文中高亮。</p>
  <el-empty v-if="!evidence.length" description="当前参考范围没有可展示的候选证据" />
  <section v-for="item in evidence" :key="item.evidenceId" class="evidence-card">
    <div class="section-heading">
      <strong>{{ item.sourceTitle }}</strong>
      <el-tag :type="item.acceptedCandidate ? 'warning' : 'info'" effect="plain">{{ item.acceptedCandidate ? '符合字面证据条件' : item.semanticSummary ? '尚无符合条件的字面片段' : '召回候选，未达字面条件' }}</el-tag>
      <el-tag v-if="item.semanticSummary?.suspectedReuse" type="warning">疑似语义复用</el-tag>
    </div>
    <p class="muted">来源{{ item.sourceWorkId }} / 修订{{ item.sourceRevisionId }} · {{ item.sourceKind === 'IMAGE_OCR' ? '来源图片OCR文字' : '来源正文' }} · TF-IDF {{ item.tfidfScore.toFixed(4) }}</p>
    <a v-if="item.sourceUrl" :href="item.sourceUrl" target="_blank" rel="noopener noreferrer">{{ item.sourceUrl }}</a>
    <p v-else-if="item.sourceMetadata?.description">{{ item.sourceMetadata.description }}</p>
    <p>字面匹配{{ item.literalSummary.matched_characters }}个字符 · 查询字面覆盖{{ (item.literalSummary.query_character_coverage * 100).toFixed(1) }}% · 最长片段{{ item.literalSummary.longest_match }}字</p>
    <p v-if="item.semanticSummary?.status === 'EVALUATED'" :class="{ unsaved: item.semanticSummary.suspectedReuse }">
      {{ item.semanticSummary.suspectedReuse ? '发现多处语义相近片段。' : '语义比对已完成。' }}
      支持片段{{ item.semanticSummary.supportingPairs }}组，涉及本稿{{ item.semanticSummary.matchedQueryCharacters }}个字符。
    </p>
    <div v-for="(match, index) in item.matches" :key="`${item.evidenceId}-${index}`" class="match-block">
      <div class="match-pair"><div><span class="muted">本稿片段 [{{ match.queryStart }}, {{ match.queryEnd }})</span><p><mark>{{ match.queryText }}</mark></p></div><div><span class="muted">来源片段 [{{ match.sourceStart }}, {{ match.sourceEnd }})</span><p><mark>{{ match.sourceText }}</mark></p></div></div>
      <el-button v-if="allowLocate" size="small" @click="$emit('locate', match.queryStart, match.queryEnd)">定位正文</el-button>
    </div>
    <el-collapse v-if="item.semanticWindows.length">
      <el-collapse-item :title="item.semanticSummary ? '句子对齐语义证据' : 'BERT部分窗口语义辅助'">
        <p v-if="item.semanticSummary" class="muted">按语义分数展示前{{ Math.min(6, item.semanticWindows.length) }}组片段。</p>
        <div v-for="(window, index) in item.semanticWindows.slice(0, 6)" :key="index" class="semantic-window">
          <p>BERT分数 {{ window.score.toFixed(4) }}</p>
          <div class="match-pair"><p>{{ window.queryText }}</p><p>{{ window.sourceText }}</p></div>
          <el-button v-if="allowLocate" size="small" @click="$emit('locate', window.queryStart, window.queryEnd)">定位语义片段</el-button>
        </div>
      </el-collapse-item>
    </el-collapse>
    <el-collapse v-if="item.sourceKind === 'IMAGE_OCR' && item.sourceMetadata?.ocr && item.sourceMetadata.sourceFileId" v-model="expandedSources">
      <el-collapse-item :name="item.evidenceId" title="来源图片与OCR区域"><OcrEvidence v-if="expandedSources.includes(item.evidenceId)" :result="item.sourceMetadata.ocr" :file-id="item.sourceMetadata.sourceFileId" source /></el-collapse-item>
    </el-collapse>
    <small class="muted evidence-id">证据 {{ item.evidenceId }}</small>
  </section>
</template>
