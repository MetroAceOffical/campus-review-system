<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { ElMessage } from 'element-plus'
import { CampusImage, StableNodeIdentities, insertUploadedImage } from '../editor/CampusImage'
import { normalizeNodeIdentities, replaceImage } from '../editor/document'
import { request } from '../api/http'
import type { DocumentInput, DocumentNode, UploadedFile } from '../types/document'
const props = defineProps<{ modelValue: DocumentInput; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: DocumentInput]; uploading: [busy: boolean]; uploadError: [failed: boolean] }>()
const failedUpload = ref(false)
function clearUploadError() { failedUpload.value = false; emit('uploadError', false) }
const fileInput = ref<HTMLInputElement>(), busy = ref(false), replacing = ref<string | null>(null)
const editor = useEditor({
  extensions: [StarterKit.configure({ heading: { levels: [2, 3] }, code: false, codeBlock: false, horizontalRule: false, strike: false, underline: false, link: { openOnClick: false, protocols: ['http', 'https'], defaultProtocol: 'https' } }), CampusImage, StableNodeIdentities],
  content: normalizeNodeIdentities(props.modelValue.content), editable: !props.disabled,
  editorProps: {
    attributes: { 'aria-label': '稿件正文' },
    handlePaste(_view, event) {
      if (event.clipboardData?.getData('text/html').match(/<img\b/i)) { ElMessage.warning('粘贴内容含图片，请将图片另行上传'); return true }
      return false
    },
  },
  onUpdate({ editor }) { emit('update:modelValue', { ...props.modelValue, content: editor.getJSON() as DocumentNode }) },
})
watch(() => props.disabled, value => editor.value?.setEditable(!value))
watch(() => props.modelValue.content, value => { if (editor.value && JSON.stringify(value) !== JSON.stringify(editor.value.getJSON())) editor.value.commands.setContent(normalizeNodeIdentities(value), { emitUpdate: false }) })
function countImages(node: DocumentNode): number { return (node.type === 'campusImage' ? 1 : 0) + (node.content?.reduce((count, child) => count + countImages(child), 0) ?? 0) }
function chooseImage(nodeId: string | null = null) { replacing.value = nodeId; fileInput.value?.click() }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file || !editor.value) return
  if (!replacing.value && countImages(editor.value.getJSON() as DocumentNode) >= 6) { ElMessage.error('每稿最多6张配图'); input.value = ''; return }
  busy.value = true; emit('uploading', true)
  try {
    const body = new FormData(); body.append('file', file)
    const result = await request<UploadedFile>('/api/files', { method: 'POST', body }); clearUploadError()
    if (replacing.value) {
      editor.value.commands.setContent(replaceImage(editor.value.getJSON() as DocumentNode, replacing.value, result.fileId))
      ElMessage.info('图片已替换，请重新确认来源')
    } else insertUploadedImage(editor.value, result.fileId)
  } catch (error) { failedUpload.value = true; emit('uploadError', true); ElMessage.error(error instanceof Error ? error.message : '上传失败，请重试') }
  finally { busy.value = false; emit('uploading', false); input.value = ''; replacing.value = null }
}
function imageReplace(event: Event) { const detail = (event as CustomEvent).detail; if (editor.value?.isEditable && detail.editor === editor.value) chooseImage(detail.nodeId) }
function setLink() { const value = window.prompt('请输入http/https链接', editor.value?.getAttributes('link').href ?? ''); if (value === null) return; if (!value) { editor.value?.chain().focus().unsetLink().run(); return }; if (!/^https?:\/\//i.test(value)) { ElMessage.error('链接须以http://或https://开头'); return }; editor.value?.chain().focus().extendMarkRange('link').setLink({ href: value }).run() }
onMounted(() => window.addEventListener('campus-replace-image', imageReplace))
onBeforeUnmount(() => window.removeEventListener('campus-replace-image', imageReplace))
</script>
<template>
  <el-alert v-if="failedUpload" title="本次图片上传失败，尚未加入正文。请重新上传，或明确忽略本次上传后再送审。" type="error" :closable="false"><el-button size="small" @click="clearUploadError">忽略本次失败上传</el-button></el-alert>
  <section class="editor-frame"><div v-if="editor && !disabled" class="editor-toolbar">
    <el-button size="small" :class="{ active: editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()">加粗</el-button><el-button size="small" @click="editor.chain().focus().toggleItalic().run()">斜体</el-button><el-button size="small" @click="editor.chain().focus().setParagraph().run()">正文</el-button><el-button size="small" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">二级标题</el-button><el-button size="small" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">三级标题</el-button><el-button size="small" @click="editor.chain().focus().toggleBulletList().run()">无序列表</el-button><el-button size="small" @click="editor.chain().focus().toggleOrderedList().run()">有序列表</el-button><el-button size="small" @click="editor.chain().focus().toggleBlockquote().run()">引用块</el-button><el-button size="small" @click="setLink">链接</el-button><el-button size="small" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()">撤销</el-button><el-button size="small" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()">重做</el-button><el-button size="small" :loading="busy" @click="chooseImage()">上传图片</el-button>
  </div><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="upload"><EditorContent :editor="editor" /></section>
</template>
