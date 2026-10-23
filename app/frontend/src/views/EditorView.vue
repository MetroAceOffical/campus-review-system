<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import CampusEditor from '../components/CampusEditor.vue'
import { request } from '../api/http'
import { session } from '../session'
import type { DocumentInput, SavedDraft } from '../types/document'
import { saveDraft, submitDraft } from '../api/manuscripts'
import { limits,loadLimits,documentSize,validationMessage } from '../editor/limits'
const route = useRoute(), router = useRouter()
const value = ref<DocumentInput>({ title: '', schemaVersion: '1', content: { type: 'doc', content: [] }, sources: [] })
const revision = ref('0'), savedAt = ref(''), id = ref(''), baseline = ref(''), loading = ref(true), saving = ref(false), uploading = ref(false), error = ref('')
const submitting = ref(false), uploadError = ref(false)
let submitted = false, submissionSignature = '', submissionKey = ''
const dirty = computed(() => !!baseline.value && JSON.stringify(value.value) !== baseline.value)
const size=computed(()=>documentSize(value.value)),limitError=computed(()=>validationMessage(value.value,limits.value))
function accept(draft: SavedDraft) { value.value = { title: draft.title, schemaVersion: draft.schemaVersion, content: draft.content, sources: draft.sources }; revision.value = draft.revision; savedAt.value = draft.savedAt; baseline.value = JSON.stringify(value.value) }
async function load() {
  try {
    await loadLimits()
    id.value = String(route.params.id ?? '')
    if (route.name === 'new-manuscript') {
      const organizationId = session.user?.organizations[0]?.organizationId
      if (!organizationId) throw new Error('当前账号没有可投稿组织')
      const result = await request<{ manuscriptId: string }>('/api/manuscripts', { method: 'POST', body: JSON.stringify({ organizationId }) })
      id.value = result.manuscriptId
      await router.replace(`/manuscripts/${id.value}/edit`)
    }
    accept(await request<SavedDraft>(`/api/manuscripts/${id.value}/draft`))
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '读取失败，请重试' }
  finally { loading.value = false }
}
async function save() {
  if (saving.value || uploading.value) return
  if(limitError.value){error.value=limitError.value;return}
  saving.value = true; error.value = ''
  const sent: DocumentInput = JSON.parse(JSON.stringify(value.value))
  try {
    const result = await saveDraft(id.value, revision.value, sent)
    if (JSON.stringify(value.value) === JSON.stringify(sent)) accept(result)
    else { revision.value = result.revision; savedAt.value = result.savedAt; baseline.value = JSON.stringify({ title: result.title, schemaVersion: result.schemaVersion, content: result.content, sources: result.sources }) }
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '保存失败，当前内容仍保留' }
  finally { saving.value = false }
}
async function submit() {
  if (saving.value || submitting.value || uploading.value || uploadError.value) return
  if(limitError.value){error.value=limitError.value;return}
  try { await ElMessageBox.confirm('送审将保存当前内容并生成独立版本，待审期间不能编辑。确认送审？', '送审确认', { confirmButtonText: '送审', cancelButtonText: '继续编辑' }) } catch { return }
  submitting.value = true; error.value = ''
  const sent: DocumentInput = JSON.parse(JSON.stringify(value.value))
  const signature = JSON.stringify({ id: id.value, revision: revision.value, input: sent })
  if (signature !== submissionSignature) { submissionSignature = signature; submissionKey = crypto.randomUUID() }
  try {
    const receipt = await submitDraft(id.value, submissionKey, revision.value, sent)
    submitted = true; baseline.value = JSON.stringify(sent)
    await router.replace(`/manuscripts/${id.value}/history?submission=${receipt.submissionId}`)
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '送审未确认，当前内容仍保留，可重试同次操作' }
  finally { submitting.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || uploading.value) { event.preventDefault(); event.returnValue = '' } }
function addSource() { value.value.sources.push({ sourceId: crypto.randomUUID(), url: '' }) }
onBeforeRouteLeave(async () => { if (submitted || (!dirty.value && !uploading.value)) return true; try { await ElMessageBox.confirm('当前修改尚未保存，确认离开？', '未保存修改', { confirmButtonText: '离开', cancelButtonText: '继续编辑' }); return true } catch { return false } })
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>
<template>
  <div v-loading="loading"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-if="!loading && baseline"><div class="editor-actions panel"><span :class="{ 'unsaved': dirty }">{{ dirty ? '有未保存修改' : '已保存' }}</span><span class="muted">{{ savedAt ? `最近保存：${new Date(savedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '' }}</span><el-button :loading="saving" :disabled="uploading || submitting" @click="save">保存草稿</el-button><el-button type="primary" :loading="submitting" :disabled="uploading || uploadError || saving || submitting || !!limitError" @click="submit">送审</el-button></div>
      <section class="panel"><el-input v-model="value.title" :disabled="submitting" aria-label="稿件标题" placeholder="稿件标题"  class="article-title-input" /><el-alert v-if="limitError" :title="limitError" type="warning" :closable="false" /><CampusEditor v-model="value" :disabled="submitting" @uploading="uploading = $event" @upload-error="uploadError = $event" /><p class="muted upload-note">标题 {{ size.title }}/{{ limits?.titleCodePoints }} 字符 · 正文 {{ size.body }}/{{ limits?.bodyCodePoints }} 字符 · 图片 {{ size.images }}/{{ limits?.images }} 张。静态JPG、PNG或WebP，每张≤{{ (limits?.imageBytes??0)/1048576 }}MiB、{{ limits?.imagePixels }}像素，任边≤{{ limits?.imageSide }}像素。</p></section>
      <section class="panel"><div class="section-heading"><h2>正文来源</h2><el-button size="small" :disabled="submitting" @click="addSource">添加来源</el-button></div><div v-for="(source, index) in value.sources" :key="source.sourceId" class="source-row"><el-input v-model="source.url" :disabled="submitting" placeholder="http/https来源链接"  /><el-button :disabled="submitting" @click="value.sources.splice(index, 1)">删除</el-button></div><span v-if="!value.sources.length" class="muted">没有引用可不填写</span></section>
    </template>
  </div>
</template>
