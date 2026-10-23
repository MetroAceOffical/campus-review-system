<script setup lang="ts">
import { useRouter } from 'vue-router'
import LoginForm from '../components/LoginForm.vue'
import { home, session } from '../session'
const router = useRouter()
function authenticated() { if (session.user) router.replace(home(session.user.role)) }
</script>
<template>
  <main class="login-page"><section class="login-panel"><div class="eyebrow">南京传媒学院 · 校园内容</div><h1>图文审核</h1><p class="muted">登录后进入工作空间</p><LoginForm @authenticated="authenticated" /></section></main>
</template>
