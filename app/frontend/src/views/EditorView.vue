<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import CampusEditor from '../components/CampusEditor.vue'
import DocumentChecks from '../components/DocumentChecks.vue'
import type { GrammarIssue } from '../api/checks'
import { codePointRangeToEditorRange, documentPositionMap, plainText } from '../editor/positions'
import { request } from '../api/http'
import { session } from '../session'
import type { DocumentInput, SavedDraft } from '../types/document'
import { saveDraft, submitDraft } from '../api/manuscripts'
import { limits,loadLimits,documentSize,validationMessage } from '../editor/limits'
const route = useRoute(), router = useRouter()
const editorRef = ref<InstanceType<typeof CampusEditor>>()
const panel = computed(() => ['content','grammar','image'].includes(String(route.query.panel)) ? String(route.query.panel) : 'content')
function changePanel(next: string | number | boolean | undefined) { void router.replace({ query: { ...route.query, panel: String(next) } }) }
function locateRange(start: number, end: number) { const ranges = codePointRangeToEditorRange(value.value.content, documentPositionMap(value.value.content), start, end); if (ranges.length) editorRef.value?.locate(ranges[0]!.from, ranges.at(-1)!.to) }
function applySuggestion(issue: GrammarIssue) { if (submitting.value) return false; if (issue.field === 'TITLE') { const chars = Array.from(value.value.title); if (chars.slice(issue.start,issue.end).join('') !== issue.original) { error.value = '标题已变化，请重新检查'; return false }; chars.splice(issue.start,issue.end-issue.start,...Array.from(issue.replacement));value.value.title=chars.join('');return true }
  const map = documentPositionMap(value.value.content), ranges = codePointRangeToEditorRange(value.value.content,map,issue.start,issue.end); if (issue.start === issue.end) { const point = map.find(entry => entry.plainStart <= issue.start && entry.plainEnd >= issue.start); if (!point) return false; const anchor = codePointRangeToEditorRange(value.value.content,map,Math.max(point.plainStart,issue.start-1),Math.min(point.plainEnd,issue.start+1)); if (!anchor.length) return false; const position = issue.start < point.plainEnd ? codePointRangeToEditorRange(value.value.content,map,issue.start,issue.start+1)[0]!.from : codePointRangeToEditorRange(value.value.content,map,issue.start-1,issue.start)[0]!.to; editorRef.value?.replaceRange(position,position,issue.replacement);return true }
  if (!ranges.length) return false; const plain = plainText(value.value.content);if(Array.from(plain).slice(issue.start,issue.end).join('')!==issue.original){error.value='正文已变化，请重新检查';return false}editorRef.value?.replaceRange(ranges[0]!.from,ranges.at(-1)!.to,issue.replacement);return true }
const value = ref<DocumentInput>({ title: '', schemaVersion: '1', content: { type: 'doc', content: [] }, sources: [] })
const revision = ref('0'), savedAt = ref(''), id = ref(''), baseline = ref(''), loading = ref(true), saving = ref(false), uploading = ref(false), error = ref('')
const submitting = ref(false), uploadError = ref(false)
let submitted = false, submissionSignature = '', submissionKey = '',disposed=false
const dirty = computed(() => !!baseline.value && JSON.stringify(value.value) !== baseline.value)
const size=computed(()=>documentSize(value.value)),limitError=computed(()=>validationMessage(value.value,limits.value))
function accept(draft: SavedDraft) { value.value = { title: draft.title, schemaVersion: draft.schemaVersion, content: draft.content, sources: draft.sources }; revision.value = draft.revision; savedAt.value = draft.savedAt; baseline.value = JSON.stringify(value.value) }
async function load() {
  try {
    await loadLimits()
    if(disposed)return
    id.value = String(route.params.id ?? '')
    if (route.name === 'new-manuscript') {
      const organizationId = session.user?.organizations[0]?.organizationId
      if (!organizationId) throw new Error('当前账号没有可投稿组织')
      const result = await request<{ manuscriptId: string }>('/api/manuscripts', { method: 'POST', body: JSON.stringify({ organizationId }) })
      if(disposed)return
      id.value = result.manuscriptId
      await router.replace({ path: `/manuscripts/${id.value}/edit`, query: route.query })
      return // AppLayout mounts the new draft route with a fresh component identity.
    }
    const draft=await request<SavedDraft>(`/api/manuscripts/${id.value}/draft`);if(!disposed){accept(draft);if(session.user)sessionStorage.setItem(`workspace-draft:${session.user.userId}`,id.value)}
  } catch (failure) { if(!disposed)error.value = failure instanceof Error ? failure.message : '读取失败，请重试' }
  finally { if(!disposed)loading.value = false }
}
async function save() {
  if (saving.value || uploading.value) return
  if(limitError.value){error.value=limitError.value;return}
  saving.value = true; error.value = ''
  const sent: DocumentInput = JSON.parse(JSON.stringify(value.value))
  try {
    const result = await saveDraft(id.value, revision.value, sent)
    if(disposed)return
    if (JSON.stringify(value.value) === JSON.stringify(sent)) accept(result)
    else { revision.value = result.revision; savedAt.value = result.savedAt; baseline.value = JSON.stringify({ title: result.title, schemaVersion: result.schemaVersion, content: result.content, sources: result.sources }) }
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '保存失败，当前内容仍保留' }
  finally { saving.value = false }
}
async function submit() {
  if (saving.value || submitting.value || uploading.value || uploadError.value) return
  if(limitError.value){error.value=limitError.value;return}
  try { await ElMessageBox.confirm('送审将保存当前内容并生成独立版本，待审期间不能编辑。确认送审？', '送审确认', { confirmButtonText: '送审', cancelButtonText: '继续编辑' }) } catch { return }
  if(disposed)return
  submitting.value = true; error.value = ''
  const sent: DocumentInput = JSON.parse(JSON.stringify(value.value))
  const signature = JSON.stringify({ id: id.value, revision: revision.value, input: sent })
  if (signature !== submissionSignature) { submissionSignature = signature; submissionKey = crypto.randomUUID() }
  try {
    const receipt = await submitDraft(id.value, submissionKey, revision.value, sent)
    if(disposed)return
    submitted = true; baseline.value = JSON.stringify(sent)
    await router.replace(`/manuscripts/${id.value}/history?submission=${receipt.submissionId}`)
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '送审未确认，当前内容仍保留，可重试同次操作' }
  finally { submitting.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || uploading.value) { event.preventDefault(); event.returnValue = '' } }
function addSource() { value.value.sources.push({ sourceId: crypto.randomUUID(), url: '' }) }
async function confirmLeave() { if (submitted || (!dirty.value && !uploading.value)) return true; try { await ElMessageBox.confirm('当前修改尚未保存，确认离开？', '未保存修改', { confirmButtonText: '离开', cancelButtonText: '继续编辑' }); return true } catch { return false } }
onBeforeRouteLeave(confirmLeave)
onBeforeRouteUpdate((to,from)=>to.path===from.path?true:confirmLeave())
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => {disposed=true;window.removeEventListener('beforeunload', beforeUnload)})
</script>
<template>
  <div v-loading="loading"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-if="!loading && baseline"><div class="editor-actions panel"><span :class="{ 'unsaved': dirty }">{{ dirty ? '有未保存修改' : '已保存' }}</span><span class="muted">{{ savedAt ? `最近保存：${new Date(savedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '' }}</span><el-button :loading="saving" :disabled="uploading || submitting" @click="save">保存草稿</el-button><el-button type="primary" :loading="submitting" :disabled="uploading || uploadError || saving || submitting || !!limitError" @click="submit">送审</el-button></div>
      <div class="shared-workspace"><div class="writing-column"><section class="panel"><el-input v-model="value.title" :disabled="submitting" aria-label="稿件标题" placeholder="稿件标题"  class="article-title-input" /><el-alert v-if="limitError" :title="limitError" type="warning" :closable="false" /><CampusEditor ref="editorRef" v-model="value" :disabled="submitting" @uploading="uploading = $event" @upload-error="uploadError = $event" /><p class="muted upload-note">标题 {{ size.title }}/{{ limits?.titleCodePoints }} 字符 · 正文 {{ size.body }}/{{ limits?.bodyCodePoints }} 字符 · 图片 {{ size.images }}/{{ limits?.images }} 张。静态JPG、PNG或WebP，每张≤{{ (limits?.imageBytes??0)/1048576 }}MiB、{{ limits?.imagePixels }}像素，任边≤{{ limits?.imageSide }}像素。</p></section>
      <section class="panel"><div class="section-heading"><h2>正文来源</h2><el-button size="small" :disabled="submitting" @click="addSource">添加全文来源</el-button></div><div v-for="source in value.sources" :key="source.sourceId" class="source-row"><RouterLink v-if="source.kind === 'INTERNAL'" :to="`/sources/${source.revisionId}`">{{ source.title }} · 站内版本{{ source.revisionId }}</RouterLink><el-input v-else v-model="source.url" :disabled="submitting" placeholder="http/https来源链接" /><el-button :disabled="submitting" @click="editorRef?.removeSource(source.sourceId)">删除来源及标记</el-button></div><span v-if="!value.sources.length" class="muted">选择正文片段可添加来源</span></section></div><aside class="panel checks-column"><el-radio-group :model-value="panel" @change="changePanel"><el-radio-button value="content">内容审核</el-radio-button><el-radio-button value="grammar">语法检查</el-radio-button><el-radio-button value="image">图文一致性</el-radio-button></el-radio-group><DocumentChecks :manuscript-id="id" :document="value" :panel="panel" :apply="applySuggestion" @locate="locateRange" /></aside></div>
    </template>
  </div>
</template>

<style scoped>.shared-workspace{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(370px,1fr);gap:18px;align-items:start}.writing-column{min-width:0;max-height:calc(100vh - 220px);overflow:auto}.checks-column{min-width:0;max-height:calc(100vh - 220px);overflow:auto}.checks-column>.el-radio-group{margin-bottom:20px}@media(max-width:1100px){.shared-workspace{grid-template-columns:minmax(0,1fr)}.writing-column,.checks-column{max-height:none}}</style>
