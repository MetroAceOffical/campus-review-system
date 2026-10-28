<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { session } from '../session'
import { request } from '../api/http'
import { listManuscripts } from '../api/manuscripts'
const route=useRoute(),router=useRouter(),error=ref('')
onMounted(async()=>{try {const panel=String(route.params.panel),last=sessionStorage.getItem(`workspace-draft:${session.user?.userId}`);if(last){try{await request(`/api/manuscripts/${last}/draft`);await router.replace({path:`/manuscripts/${last}/edit`,query:{panel}});return}catch{}}
  const rows=await listManuscripts(1,'','');const draft=rows.items.find(row=>['DRAFT','RETURNED'].includes(row.status));await router.replace({path:draft?`/manuscripts/${draft.manuscriptId}/edit`:'/manuscripts/new',query:{panel}})
}catch(value){error.value=value instanceof Error?value.message:'读取稿件失败'}})
</script>
<template><p v-if="error" role="alert">{{error}}</p><p v-else>正在打开共用稿件工作区…</p></template>
