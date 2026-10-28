<script setup lang="ts">
import type { ImageEvidenceItem } from '../api/review'
import GeometryImage from './GeometryImage.vue'
defineProps<{ evidence: ImageEvidenceItem[]; queryFileId: string; imageNumber: number }>()
const percentage = (value?: number) => value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
function label(item: ImageEvidenceItem) {
  if (!item.geometry) return item.acceptedCandidate ? '相似图片' : '未达到阈值'
  if (item.geometry.status === 'SOURCE_UNAVAILABLE') return '来源图片不可读'
  if (!item.geometry.acceptedCorrespondence) return '几何证据不足'
  return item.geometry.scope === 'LOCAL_REGION' ? '局部对应' : '整图对应'
}
</script>
<template>
  <el-empty v-if="!evidence.length" description="当前参考范围没有图片候选" />
  <section v-for="item in evidence" :key="item.evidenceId" class="evidence-card">
    <div class="section-heading"><strong>{{ item.sourceTitle }}</strong><el-tag :type="item.acceptedCandidate ? 'warning' : 'info'">{{ label(item) }}</el-tag></div>
    <p>余弦相似度 {{ item.similarity.toFixed(4) }}<template v-if="!item.geometry"> · 匹配阈值 {{ item.threshold.toFixed(4) }}</template></p>
    <div v-if="item.geometry" class="geometry-stats"><div><span>几何内点</span><strong>{{ item.geometry.inliers ?? '—' }} <small>/ {{ item.geometry.matches ?? '—' }}</small></strong></div><div><span>本稿对应区域覆盖</span><strong>{{ percentage(item.geometry.querySpatialCoverage) }}</strong></div><div><span>来源对应区域覆盖</span><strong>{{ percentage(item.geometry.sourceSpatialCoverage) }}</strong></div></div>
    <p v-if="item.geometry?.identityBasis" class="muted">{{ item.geometry.identityBasis === 'FILE_SHA256' ? '文件指纹一致' : '解码像素一致' }}</p>
    <div class="image-pair"><figure><GeometryImage :file-id="queryFileId" :label="`本稿配图${imageNumber}对应区域`" :size="item.geometry?.querySize" :region="item.geometry?.queryRegion" /><figcaption>本稿配图{{ imageNumber }}</figcaption></figure><figure><GeometryImage :file-id="item.sourceFileId" label="来源图片对应区域" :size="item.geometry?.sourceSize" :region="item.geometry?.sourceRegion" /><figcaption>来源图片 · 作品{{ item.sourceWorkId }} / 修订{{ item.sourceRevisionId }}</figcaption></figure></div>
    <a v-if="item.sourceUrl" :href="item.sourceUrl" target="_blank" rel="noopener noreferrer">来源页面</a><small class="muted evidence-id">证据 {{ item.evidenceId }}</small>
  </section>
</template>
<style scoped>.geometry-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}.geometry-stats>div{padding:14px;background:color-mix(in srgb,var(--el-color-primary) 6%,var(--canvas))}.geometry-stats span{font-size:12px;color:var(--muted)}.geometry-stats strong{display:block;font-size:24px;margin-top:6px}.geometry-stats small{font-size:13px;font-weight:400}@media(max-width:650px){.geometry-stats{grid-template-columns:1fr}}</style>
