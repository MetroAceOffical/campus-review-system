<script setup lang="ts">
import { onMounted,ref } from 'vue'
import { useRoute } from 'vue-router'
import ReadOnlyDocument from '../components/ReadOnlyDocument.vue'
import { getPublication,type Publication } from '../api/references'
const route=useRoute(),publication=ref<Publication>(),loading=ref(true),error=ref('')
onMounted(async()=>{try{publication.value=await getPublication(String(route.params.id))}catch(failure){error.value=failure instanceof Error?failure.message:'读取失败'}finally{loading.value=false}})
</script>
<template><el-alert v-if="error" :title="error" type="error" :closable="false" /><div class="panel"><RouterLink to="/publications">返回已发布稿件</RouterLink></div><section v-loading="loading" class="panel published-article"><template v-if="publication"><p class="publication-meta">{{ publication.organizationName }} · {{ new Date(publication.publishedAt).toLocaleString('zh-CN') }}</p><ReadOnlyDocument :document="publication" /></template></section></template>
