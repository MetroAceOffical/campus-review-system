<script setup lang="ts">
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { computed } from 'vue'
import { moveImage } from '../editor/document'
import type { DocumentNode } from '../types/document'
const props = defineProps(nodeViewProps)
const imageNumber = computed(() => { let number = 0, current = 0; props.editor.state.doc.descendants(node => { if (node.type.name === 'campusImage') { current++; if (node.attrs.nodeId === props.node.attrs.nodeId) number = current } }); return number })
function move(direction: -1 | 1) { props.editor.commands.setContent(moveImage(props.editor.getJSON() as DocumentNode, props.node.attrs.nodeId, direction)) }
function replace() { window.dispatchEvent(new CustomEvent('campus-replace-image', { detail: { editor: props.editor, nodeId: props.node.attrs.nodeId } })) }
</script>
<template>
  <NodeViewWrapper as="figure" class="campus-image" :class="{ selected }" contenteditable="false">
    <div v-if="editor.isEditable" class="image-tools"><span data-drag-handle>配图 {{ imageNumber }} · 拖动调整位置</span><div><el-button size="small" @click="move(-1)">上移</el-button><el-button size="small" @click="move(1)">下移</el-button><el-button size="small" @click="replace">替换</el-button><el-button size="small" type="danger" plain @click="deleteNode">删除</el-button></div></div>
    <img :src="`/api/files/${node.attrs.fileId}`" :alt="node.attrs.caption || `配图${imageNumber}`">
    <div v-if="editor.isEditable" class="image-metadata"><el-input :model-value="node.attrs.caption" placeholder="图注（可选）" maxlength="1000" @update:model-value="(value: string) => updateAttributes({ caption: value })" /><el-select :model-value="node.attrs.origin" placeholder="选择图片来源" @update:model-value="(value: string) => updateAttributes({ origin: value })"><el-option label="原创" value="ORIGINAL" /><el-option label="引用" value="CITED" /></el-select><el-input v-if="node.attrs.origin === 'CITED'" :model-value="node.attrs.sourceUrl" placeholder="来源链接（http/https）"  @update:model-value="(value: string) => updateAttributes({ sourceUrl: value })" /></div>
    <figcaption v-else>{{ node.attrs.caption }}<span v-if="node.attrs.origin === 'CITED'"> · 来源：{{ node.attrs.sourceUrl }}</span></figcaption>
  </NodeViewWrapper>
</template>
