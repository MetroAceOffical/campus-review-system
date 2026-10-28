<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api/http'
import type { DocumentInput } from '../types/document'
import ReadOnlyDocument from '../components/ReadOnlyDocument.vue'
const route = useRoute(), value = ref<DocumentInput>(), error = ref('')
onMounted(async () => { try { value.value = await request(`/api/citation-sources/${route.params.id}`) } catch (e) { error.value = e instanceof Error ? e.message : '来源读取失败' } })
</script>
<template><section class="panel"><p v-if="error" role="alert">{{ error }}</p><ReadOnlyDocument v-if="value" :document="value" /><span v-else-if="!error">正在读取来源…</span></section></template>
