<script setup lang="ts">
import { computed } from 'vue'
import type { TextEvidenceItem } from '../api/review'
import TextSourceEvidence from './TextSourceEvidence.vue'
const props = defineProps<{ evidence: TextEvidenceItem[]; allowLocate?: boolean }>()
const emit = defineEmits<{ locate: [start: number, end: number] }>()
const important = (item: TextEvidenceItem) => item.fullyCited || item.acceptedCandidate || item.semanticSummary?.suspectedReuse
const primary = computed(() => props.evidence.filter(important))
const other = computed(() => props.evidence.filter(item => !important(item)))
</script>
<template>
  <p class="muted">核对投稿与来源片段，点击定位可查看正文位置。</p>
  <el-empty v-if="!evidence.length" description="当前参考范围没有可展示的候选证据" />
  <div v-if="primary.length" data-testid="primary-text-evidence"><TextSourceEvidence v-for="item in primary" :key="item.evidenceId" :item="item" :allow-locate="allowLocate" @locate="(start,end) => emit('locate',start,end)" /></div>
  <p v-else-if="evidence.length" class="muted">本次比对没有触发文字复用提示。</p>
  <details v-if="other.length" data-testid="other-text-candidates" class="other-text-candidates"><summary>其他检索候选 · {{ other.length }}个来源</summary><TextSourceEvidence v-for="item in other" :key="item.evidenceId" :item="item" :allow-locate="allowLocate" @locate="(start,end) => emit('locate',start,end)" /></details>
</template>
<style scoped>.other-text-candidates{border:1px solid var(--line);padding:16px;margin-top:18px}.other-text-candidates>summary{cursor:pointer;font-weight:600}</style>
