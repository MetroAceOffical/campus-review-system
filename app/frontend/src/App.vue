<script setup lang="ts">
import { onSessionExpired } from './api/http'
import { session } from './session'
import LoginForm from './components/LoginForm.vue'
onSessionExpired(() => { if (session.user) session.expired = true })
</script>
<template>
  <RouterView />
  <el-dialog v-model="session.expired" title="请重新登录" width="380px" :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false" destroy-on-close>
    <p class="muted">登录已过期，当前编辑内容仍保留。登录后可重试原操作。</p><LoginForm />
  </el-dialog>
</template>
