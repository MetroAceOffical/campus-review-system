<script setup lang="ts">
import { h, type VNodeChild } from 'vue'
import type { DocumentInput, DocumentNode } from '../types/document'
import type { EditorRange } from '../editor/positions'
const props = defineProps<{ document: DocumentInput; highlights?: EditorRange[] }>()
const url = (value: unknown) => typeof value === 'string' && /^https?:\/\//i.test(value) ? value : undefined
function content() {
  let image = 0, currentNode = '', offset = 0
  function node(value: DocumentNode): VNodeChild {
    const attrs = value.attrs ?? {}, children = () => value.content?.map(node) ?? []
    if (value.type === 'text') {
      let result: VNodeChild = value.text ?? ''
      const text = value.text ?? '', start = offset; offset += text.length
      const ranges = (props.highlights ?? []).filter(range => range.nodeId === currentNode && range.nodeFrom < offset && range.nodeTo > start)
      if (ranges.length) {
        const cuts = Array.from(new Set([0, text.length, ...ranges.flatMap(range => [Math.max(0, range.nodeFrom - start), Math.min(text.length, range.nodeTo - start)])])).sort((a, b) => a - b)
        result = cuts.slice(0, -1).map((from, index) => { const to = cuts[index + 1]!; return ranges.some(range => range.nodeFrom < start + to && range.nodeTo > start + from) ? h('mark', { class: 'literal-match' }, text.slice(from, to)) : text.slice(from, to) })
      }
      for (const mark of value.marks ?? []) {
        if (mark.type === 'bold') result = h('strong', {}, result)
        if (mark.type === 'italic') result = h('em', {}, result)
        if (mark.type === 'link') result = h('a', { href: url(mark.attrs?.href), target: '_blank', rel: 'noopener noreferrer' }, result)
        if (mark.type === 'citation') { const ids = Array.isArray(mark.attrs?.sourceIds) ? mark.attrs.sourceIds as string[] : []; const sources = props.document.sources.filter(source => ids.includes(source.sourceId)); result = h('span', { class: 'citation-text', title: sources.map(source => source.title || source.url).join(' / ') }, result) }
      }
      return result
    }
    if (value.type === 'hardBreak') { offset++; return h('br') }
    if (value.type === 'campusImage') {
      image++
      return h('figure', { class: 'article-image', 'data-node-id': attrs.nodeId }, [h('img', { src: `/api/files/${attrs.fileId}`, alt: String(attrs.caption || `配图${image}`) }), h('figcaption', {}, `图${image} ${attrs.caption ?? ''}`), h('p', { class: 'image-origin' }, attrs.origin === 'ORIGINAL' ? '声明：原创' : [ '来源：', h('a', { href: url(attrs.sourceUrl), target: '_blank', rel: 'noopener noreferrer' }, String(attrs.sourceUrl ?? '')) ])])
    }
    const tags: Record<string, string> = { paragraph: 'p', heading: attrs.level === 3 ? 'h3' : 'h2', bulletList: 'ul', orderedList: 'ol', listItem: 'li', blockquote: 'blockquote', doc: 'div' }
    if (value.type === 'paragraph' || value.type === 'heading') { currentNode = String(attrs.nodeId); offset = 0 }
    return h(tags[value.type] ?? 'div', { 'data-node-id': attrs.nodeId, ...(value.type === 'orderedList' ? { start: attrs.start, type: attrs.type } : {}) }, children())
  }
  return h('div', { class: 'article-body' }, [node(props.document.content)])
}
</script>
<template><article><h2 class="article-title">{{ document.title }}</h2><component :is="content" /><section v-if="document.sources.length" class="article-sources"><h3>正文来源</h3><p v-for="source in document.sources" :key="source.sourceId"><RouterLink v-if="source.kind === 'INTERNAL'" :to="`/sources/${source.revisionId}`">{{ source.title }} · 站内版本{{ source.revisionId }}</RouterLink><a v-else :href="url(source.url)" target="_blank" rel="noopener noreferrer">{{ source.title || source.url }}</a></p></section></article></template>
