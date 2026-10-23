<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import CampusEditor from '../components/CampusEditor.vue'
import { request } from '../api/http'
import { session } from '../session'
import type { DocumentInput, SavedDraft } from '../types/document'
const route = useRoute(), router = useRouter()
const value = ref<DocumentInput>({ title: '', schemaVersion: '1', content: { type: 'doc', content: [] }, sources: [] })
const revision = ref('0'), savedAt = ref(''), id = ref(''), baseline = ref(''), loading = ref(true), saving = ref(false), uploading = ref(false), error = ref('')
const dirty = computed(() => !!baseline.value && JSON.stringify(value.value) !== baseline.value)
function accept(draft: SavedDraft) { value.value = { title: draft.title, schemaVersion: draft.schemaVersion, content: draft.content, sources: draft.sources }; revision.value = draft.revision; savedAt.value = draft.savedAt; baseline.value = JSON.stringify(value.value) }
async function load() {
  try {
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
  saving.value = true; error.value = ''
  const sent: DocumentInput = JSON.parse(JSON.stringify(value.value))
  try {
    const result = await request<SavedDraft>(`/api/manuscripts/${id.value}/draft`, { method: 'PUT', body: JSON.stringify({ ...sent, expectedRevision: revision.value }) })
    if (JSON.stringify(value.value) === JSON.stringify(sent)) accept(result)
    else { revision.value = result.revision; savedAt.value = result.savedAt; baseline.value = JSON.stringify({ title: result.title, schemaVersion: result.schemaVersion, content: result.content, sources: result.sources }) }
  } catch (failure) { error.value = failure instanceof Error ? failure.message : '保存失败，当前内容仍保留' }
  finally { saving.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || uploading.value) { event.preventDefault(); event.returnValue = '' } }
function addSource() { value.value.sources.push({ sourceId: crypto.randomUUID(), url: '' }) }
onBeforeRouteLeave(async () => { if (!dirty.value && !uploading.value) return true; try { await ElMessageBox.confirm('当前修改尚未保存，确认离开？', '未保存修改', { confirmButtonText: '离开', cancelButtonText: '继续编辑' }); return true } catch { return false } })
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>
<template>
  <div v-loading="loading"><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <template v-if="!loading && baseline"><div class="editor-actions panel"><span :class="{ 'unsaved': dirty }">{{ dirty ? '有未保存修改' : '已保存' }}</span><span class="muted">{{ savedAt ? `最近保存：${new Date(savedAt).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}` : '' }}</span><el-button type="primary" :loading="saving" :disabled="uploading" @click="save">保存草稿</el-button></div>
      <section class="panel"><el-input v-model="value.title" aria-label="稿件标题" placeholder="稿件标题" maxlength="400" class="article-title-input" /><CampusEditor v-model="value" @uploading="uploading = $event" /><p class="muted upload-note">最多6张静态JPG、PNG或WebP；每张不超过10MiB、2000万像素，任一边不超过8000像素。</p></section>
      <section class="panel"><div class="section-heading"><h2>正文来源</h2><el-button size="small" @click="addSource">添加来源</el-button></div><div v-for="(source, index) in value.sources" :key="source.sourceId" class="source-row"><el-input v-model="source.url" placeholder="http/https来源链接" maxlength="2000" /><el-button @click="value.sources.splice(index, 1)">删除</el-button></div><span v-if="!value.sources.length" class="muted">没有引用可不填写</span></section>
    </template>
  </div>
</template>
