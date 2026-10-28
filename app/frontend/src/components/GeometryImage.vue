<script setup lang="ts">
defineProps<{ fileId: string; label: string; size?: { width:number; height:number }; region?: number[][] }>()
const points = (region: number[][]) => region.map(point => point.join(',')).join(' ')
</script>
<template>
  <div v-if="size && size.width > 0 && size.height > 0 && region?.length" class="geometry-image" :style="{aspectRatio: `${size.width} / ${size.height}`}">
    <el-image :src="`/api/files/${fileId}`" :preview-src-list="[`/api/files/${fileId}`]" :alt="label" fit="contain" />
    <svg :viewBox="`0 0 ${size.width} ${size.height}`" role="img" :aria-label="label"><polygon :points="points(region)" vector-effect="non-scaling-stroke"><title>{{ label }}</title></polygon></svg>
  </div>
  <el-image v-else :src="`/api/files/${fileId}`" :preview-src-list="[`/api/files/${fileId}`]" :alt="label" fit="contain" />
</template>
<style scoped>.geometry-image{position:relative;width:100%;max-height:480px}.geometry-image .el-image{width:100%;height:100%}.geometry-image svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.geometry-image polygon{fill:rgb(33 93 186 / 18%);stroke:#215dba;stroke-width:2}</style>
