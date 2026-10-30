<script setup lang="ts">
import RecordPagination from './RecordPagination.vue'
const citationSize = ref(10)
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { ElMessage } from 'element-plus'
import { CampusImage, StableNodeIdentities, insertUploadedImage } from '../editor/CampusImage'
import { normalizeNodeIdentities, replaceImage } from '../editor/document'
import { request } from '../api/http'
import type { DocumentInput, DocumentNode, UploadedFile, Source } from '../types/document'
import { Citation } from '../editor/Citation'
import { limits,loadLimits } from '../editor/limits'
const props = defineProps<{ modelValue: DocumentInput; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: DocumentInput]; uploading: [busy: boolean]; uploadError: [failed: boolean] }>()
const failedUpload = ref(false)
function clearUploadError() { failedUpload.value = false; emit('uploadError', false) }
const fileInput = ref<HTMLInputElement>(), busy = ref(false), replacing = ref<string | null>(null)
const citationOpen = ref(false), citationKind = ref<'INTERNAL' | 'EXTERNAL'>('INTERNAL'), citationUrl = ref(''), citationTitle = ref(''), citationQuery = ref(''), citationDepartment = ref(''), citationPage = ref(1), citationTotal = ref(0), citationError = ref(''), selectedQuote = ref('')
const citationRows = ref<Array<{ workId: string; revisionId: string; title: string; preview: string; department: string }>>([]), sourceChoice = ref<{ workId: string; revisionId: string; title: string } | null>(null)
const citationDepartments = ref<Array<{ id: string; name: string }>>([])
let selectionFrom = 0, selectionTo = 0, selectionDocument: unknown
const lastSelectionText = ref(''), selectionStyle = ref({ left: '0px', top: '0px' })
let disposed=false
const editor = useEditor({
  extensions: [StarterKit.configure({ trailingNode: false, heading: { levels: [2, 3] }, code: false, codeBlock: false, horizontalRule: false, strike: false, underline: false, link: { openOnClick: false, protocols: ['http', 'https'], defaultProtocol: 'https' } }), CampusImage, StableNodeIdentities, Citation],
  content: normalizeNodeIdentities(props.modelValue.content), editable: !props.disabled,
  editorProps: {
    attributes: { 'aria-label': '稿件正文' },
    handlePaste(_view, event) {
      if (event.clipboardData?.getData('text/html').match(/<img\b/i)) { ElMessage.warning('粘贴内容含图片，请将图片另行上传'); return true }
      return false
    },
  },
  onUpdate({ editor }) { emit('update:modelValue', { ...props.modelValue, content: editor.getJSON() as DocumentNode }) },
  onSelectionUpdate({ editor }) { lastSelectionText.value = editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to, '\n'); if (lastSelectionText.value) { const point = editor.view.coordsAtPos(editor.state.selection.from); selectionStyle.value = { left: `${Math.min(point.left, window.innerWidth - 155)}px`, top: `${Math.max(8, point.top - 42)}px` } } },
})
async function searchSources() { citationError.value = ''; try { if (!citationDepartments.value.length) citationDepartments.value = await request('/api/citation-sources/departments'); const result = await request<{ items: typeof citationRows.value; total: number }>(`/api/citation-sources?q=${encodeURIComponent(citationQuery.value)}&department=${encodeURIComponent(citationDepartment.value)}&page=${citationPage.value}&pageSize=${citationSize.value}`); citationRows.value = result.items; citationTotal.value = result.total } catch (value) { citationError.value = value instanceof Error ? value.message : '来源搜索失败' } }
function openCitation() { if (!editor.value || editor.value.state.selection.empty) { ElMessage.info('请先选择要标注的正文'); return }; selectionFrom = editor.value.state.selection.from; selectionTo = editor.value.state.selection.to; selectionDocument = editor.value.state.doc; selectedQuote.value = editor.value.state.doc.textBetween(selectionFrom, selectionTo, '\n'); sourceChoice.value = null; citationUrl.value = ''; citationTitle.value = ''; citationError.value = ''; citationOpen.value = true; void searchSources() }
function attachCitation() {
  const current = editor.value; if (!current || current.state.doc !== selectionDocument) { citationError.value = '稿件已变化，请关闭后重新选择片段'; return }
  if (citationKind.value === 'INTERNAL' && !sourceChoice.value) { citationError.value = '请选择站内文章'; return }
  if (citationKind.value === 'EXTERNAL') { try { const url = new URL(citationUrl.value); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error() } catch { citationError.value = '请输入有效的http或https来源地址'; return } }
  const source: Source = citationKind.value === 'INTERNAL' ? { sourceId: crypto.randomUUID(), url: '', kind: 'INTERNAL', workId: sourceChoice.value!.workId, revisionId: sourceChoice.value!.revisionId, title: sourceChoice.value!.title } : { sourceId: crypto.randomUUID(), url: citationUrl.value, kind: 'EXTERNAL', title: citationTitle.value }
  const transaction = current.state.tr, mark = current.schema.marks.citation!
  current.state.doc.nodesBetween(selectionFrom, selectionTo, (node, position) => { if (!node.isText) return; const prior = node.marks.find(m => m.type === mark)?.attrs.sourceIds ?? []; const ids = Array.from(new Set([...prior, source.sourceId])); transaction.addMark(Math.max(position, selectionFrom), Math.min(position + node.nodeSize, selectionTo), mark.create({ sourceIds: ids })) })
  current.view.dispatch(transaction); emit('update:modelValue', { ...props.modelValue, schemaVersion: '2', content: current.getJSON() as DocumentNode, sources: [...props.modelValue.sources, source] }); citationOpen.value = false; lastSelectionText.value = ''
}
function removeSource(sourceId: string) { const current = editor.value; if (!current) return; const transaction = current.state.tr, type = current.schema.marks.citation!
  current.state.doc.descendants((node, pos) => { if (!node.isText) return; const mark = node.marks.find(m => m.type === type); if (!mark?.attrs.sourceIds.includes(sourceId)) return; const ids = mark.attrs.sourceIds.filter((id: string) => id !== sourceId); transaction.removeMark(pos, pos + node.nodeSize, type); if (ids.length) transaction.addMark(pos, pos + node.nodeSize, type.create({ sourceIds: ids })) }); current.view.dispatch(transaction); emit('update:modelValue', { ...props.modelValue, content: current.getJSON() as DocumentNode, sources: props.modelValue.sources.filter(source => source.sourceId !== sourceId) }) }
function locate(from: number, to: number) { editor.value?.chain().focus().setTextSelection({ from, to }).scrollIntoView().run() }
function replaceRange(from: number, to: number, replacement: string) { if (editor.value?.isEditable) editor.value.chain().focus().insertContentAt({ from, to }, replacement ? [{ type: 'text', text: replacement }] : []).run() }
defineExpose({ removeSource, locate, replaceRange })
watch(() => props.disabled, value => editor.value?.setEditable(!value))
watch(() => props.modelValue.content, value => { if (editor.value && JSON.stringify(value) !== JSON.stringify(editor.value.getJSON())) editor.value.commands.setContent(normalizeNodeIdentities(value), { emitUpdate: false }) })
function countImages(node: DocumentNode): number { return (node.type === 'campusImage' ? 1 : 0) + (node.content?.reduce((count, child) => count + countImages(child), 0) ?? 0) }
function chooseImage(nodeId: string | null = null) { if(busy.value||props.disabled||disposed)return;replacing.value = nodeId; fileInput.value?.click() }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file || !editor.value || busy.value || props.disabled || disposed) return
  const target=replacing.value
  if(!limits.value){ElMessage.error('输入限额尚未读取，请稍后重试');input.value='';return}
  if (!target && countImages(editor.value.getJSON() as DocumentNode) >= limits.value.images) { ElMessage.error(`每稿最多${limits.value.images}张配图`); input.value = ''; return }
  if(file.size>limits.value.imageBytes){ElMessage.error(`单图最多${limits.value.imageBytes/1048576}MiB，原编辑内容已保留`);input.value='';return}
  busy.value = true; emit('uploading', true)
  try {
    const body = new FormData(); body.append('file', file)
    const result = await request<UploadedFile>('/api/files', { method: 'POST', body });if(disposed)return;clearUploadError()
    if (target) {
      editor.value.commands.setContent(replaceImage(editor.value.getJSON() as DocumentNode, target, result.fileId))
      ElMessage.info('图片已替换，请重新确认来源')
    } else insertUploadedImage(editor.value, result.fileId)
  } catch (error) { if(!disposed){failedUpload.value = true; emit('uploadError', true); ElMessage.error(error instanceof Error ? error.message : '上传失败，请重试')} }
  finally { busy.value = false;if(!disposed)emit('uploading', false); input.value = ''; replacing.value = null }
}
function imageReplace(event: Event) { const detail = (event as CustomEvent).detail; if (editor.value?.isEditable && detail.editor === editor.value) chooseImage(detail.nodeId) }
function setLink() { const value = window.prompt('请输入http/https链接', editor.value?.getAttributes('link').href ?? ''); if (value === null) return; if (!value) { editor.value?.chain().focus().unsetLink().run(); return }; if (!/^https?:\/\//i.test(value)) { ElMessage.error('链接须以http://或https://开头'); return }; editor.value?.chain().focus().extendMarkRange('link').setLink({ href: value }).run() }
onMounted(() => {window.addEventListener('campus-replace-image', imageReplace);void loadLimits().catch(error=>ElMessage.error(error instanceof Error?error.message:'读取限额失败'))})
onBeforeUnmount(() => {disposed=true;window.removeEventListener('campus-replace-image', imageReplace)})
</script>
<template>
  <el-alert v-if="failedUpload" title="本次图片上传失败，尚未加入正文。请重新上传，或明确忽略本次上传后再送审。" type="error" :closable="false"><el-button size="small" @click="clearUploadError">忽略本次失败上传</el-button></el-alert>
  <section class="editor-frame"><div v-if="editor && !disabled" class="editor-toolbar">
    <el-button size="small" @mousedown.prevent @click="openCitation">片段来源</el-button><el-button size="small" @click="editor.chain().focus().unsetMark('citation').run()">取消所选引用</el-button>
    <el-button size="small" :class="{ active: editor.isActive('bold') }" @click="editor.chain().focus().toggleBold().run()">加粗</el-button><el-button size="small" @click="editor.chain().focus().toggleItalic().run()">斜体</el-button><el-button size="small" @click="editor.chain().focus().setParagraph().run()">正文</el-button><el-button size="small" @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">二级标题</el-button><el-button size="small" @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">三级标题</el-button><el-button size="small" @click="editor.chain().focus().toggleBulletList().run()">无序列表</el-button><el-button size="small" @click="editor.chain().focus().toggleOrderedList().run()">有序列表</el-button><el-button size="small" @click="editor.chain().focus().toggleBlockquote().run()">引用块</el-button><el-button size="small" @click="setLink">链接</el-button><el-button size="small" :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()">撤销</el-button><el-button size="small" :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()">重做</el-button><el-button size="small" :loading="busy" @click="chooseImage()">上传图片</el-button>
  </div><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" hidden @change="upload"><EditorContent :editor="editor" /></section>
  <div v-if="lastSelectionText && !citationOpen && !disabled" class="citation-float" :style="selectionStyle"><el-button size="small" type="primary" @mousedown.prevent @click="openCitation">为选中文字添加来源</el-button></div>
  <el-dialog v-model="citationOpen" title="添加片段来源" width="min(780px, 96vw)" class="citation-dialog" :close-on-click-modal="false"><blockquote class="citation-selection">{{ selectedQuote }}</blockquote><el-radio-group v-model="citationKind"><el-radio-button value="INTERNAL">站内文章</el-radio-button><el-radio-button value="EXTERNAL">站外网址</el-radio-button></el-radio-group>
    <template v-if="citationKind === 'INTERNAL'"><div class="citation-search"><el-input v-model="citationQuery" placeholder="搜索标题" aria-label="搜索引用文章" @change="citationPage = 1; searchSources()" /><el-select v-model="citationDepartment" clearable placeholder="全部部门" aria-label="来源部门" @change="citationPage = 1; searchSources()"><el-option v-for="item in citationDepartments" :key="item.id" :value="item.id" :label="item.name" /></el-select><el-button @click="citationPage = 1; searchSources()">搜索</el-button></div><div class="citation-results"><button v-for="row in citationRows" :key="row.revisionId" type="button" class="citation-choice" :class="{selected:sourceChoice?.revisionId === row.revisionId}" @click="sourceChoice = row"><strong>{{ row.title }}</strong><small>{{ row.department }} · 版本{{ row.revisionId }}</small><p>{{ row.preview }}</p></button><el-empty v-if="!citationRows.length" description="未找到可访问的文章" :image-size="55" /></div><RecordPagination v-model:current-page="citationPage" v-model:page-size="citationSize" :total="citationTotal" @change="searchSources" /></template>
    <el-form v-else label-position="top"><el-form-item label="来源网址"><el-input v-model="citationUrl" maxlength="2000" placeholder="https://" /></el-form-item><el-form-item label="来源名称（可选）"><el-input v-model="citationTitle" maxlength="200" /></el-form-item><span class="muted">站外来源由审核员核验。</span></el-form><p v-if="citationError" role="alert" class="work-error">{{ citationError }}</p><template #footer><el-button @click="citationOpen = false">取消</el-button><el-button type="primary" @click="attachCitation">添加来源</el-button></template>
  </el-dialog>
</template>
<style scoped>.citation-float{position:fixed;z-index:2000}.citation-selection{max-height:100px;overflow:auto;border-left:3px solid var(--el-color-primary);padding:10px;margin:0 0 16px;white-space:pre-wrap;font-size:13px}.citation-search{display:flex;gap:10px;margin:16px 0}.citation-results{max-height:340px;overflow:auto}.citation-choice{display:block;width:100%;padding:12px;text-align:left;border:1px solid var(--line);border-radius:0;background:var(--canvas);color:inherit;cursor:pointer;margin-bottom:8px}.citation-choice.selected{border-color:var(--el-color-primary);background:color-mix(in srgb,var(--el-color-primary) 8%,var(--canvas))}.citation-choice small{display:block;color:var(--muted);margin-top:5px}.citation-choice p{font-size:12px;line-height:1.6;margin-bottom:0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}:global(.citation-text){border-bottom:2px solid var(--el-color-primary);background:color-mix(in srgb,var(--el-color-primary) 7%,transparent)}:global(.citation-dialog){border-radius:0}</style>
