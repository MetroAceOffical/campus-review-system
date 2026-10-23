<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { session, logout } from '../session'
import { applyTheme, readTheme } from '../theme'
const route = useRoute(), router = useRouter(), theme = reactive(readTheme())
const links = computed(() => [
  ...(session.user?.role === 'MEMBER' ? [{ to: '/manuscripts', label: '组织稿件' }] : []),
  ...(session.user?.role === 'REVIEWER' ? [{ to: '/reviews', label: '审核工作台' }] : []),
  ...(session.user?.role === 'ADMIN' ? [{ to: '/experiments', label: '模型实验' }, { to: '/references', label: '参考作品' }] : []),
  { to: '/publications', label: '已发布' },
])
async function signOut() {
  try { await ElMessageBox.confirm('确认退出当前账号？', '退出登录', { confirmButtonText: '退出', cancelButtonText: '取消' }); await logout(); await router.replace('/login') }
  catch { /* User cancelled or server did not confirm logout; retain current page. */ }
}
</script>
<template>
  <div class="app-shell">
    <header class="app-header"><RouterLink to="/" class="brand">校园图文审核</RouterLink><span class="school">南京传媒学院</span><div class="header-actions">
      <el-popover trigger="click" width="260"><template #reference><el-button>外观</el-button></template>
        <div class="theme-form"><label>显示模式</label><el-select v-model="theme.mode" @change="applyTheme(theme)"><el-option label="浅色" value="light" /><el-option label="深色" value="dark" /><el-option label="跟随系统" value="system" /></el-select><label>主题色</label><div class="theme-colors"><button v-for="color in ['#215dba', '#16704a', '#7955a3', '#a34131']" :key="color" :aria-label="`使用主题色 ${color}`" :style="{ background: color }" @click="theme.primary = color; applyTheme(theme)" /><input v-model="theme.primary" aria-label="自定义主题色" type="color" @input="applyTheme(theme)" /></div></div>
      </el-popover><span>{{ session.user?.displayName }}</span><el-button @click="signOut">退出</el-button>
    </div></header>
    <div class="shell-body"><aside class="sidebar"><div class="organization-label">{{ session.user?.organizations.map(o => o.name).join(' / ') || '工作空间' }}</div><nav><RouterLink v-for="link in links" :key="link.to" :to="link.to">{{ link.label }}</RouterLink></nav></aside>
      <main class="page-content"><h1>{{ route.meta.title }}</h1><RouterView /></main>
    </div>
  </div>
</template>
