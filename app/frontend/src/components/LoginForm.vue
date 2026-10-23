<script setup lang="ts">
import { ref } from 'vue'
import { login } from '../session'
const emit = defineEmits<{ authenticated: [] }>()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function submit() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await login(username.value, password.value); password.value = ''; emit('authenticated') }
  catch (failure) { error.value = failure instanceof Error ? failure.message : '登录失败，请稍后重试' }
  finally { busy.value = false }
}
</script>
<template>
    <el-form label-position="top" method="post" action="/api/auth/login" @submit.prevent="submit">
      <el-form-item label="账号"><el-input v-model="username" name="username" autocomplete="username" maxlength="64" required /></el-form-item>
      <el-form-item label="密码"><el-input v-model="password" name="password" type="password" autocomplete="current-password" show-password required /></el-form-item>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-button type="primary" native-type="submit" :loading="busy" class="login-submit">登录</el-button>
    </el-form>
</template>
