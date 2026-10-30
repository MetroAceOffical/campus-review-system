<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import WorkflowNavigator from '../components/workbench/WorkflowNavigator.vue'
import { contextualLink } from '../workflow-context'
import { useRoute, useRouter, isNavigationFailure, NavigationFailureType } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { session, logout, home } from '../session'
import { applyTheme, readTheme } from '../theme'
const route = useRoute(), router = useRouter(), theme = reactive(readTheme())
function focusMain() { document.getElementById('main-content')?.focus() }
const navigationOpen = ref(false)
watch(() => route.fullPath, () => { navigationOpen.value = false })
const roleName = computed(() => ({ ADMIN: '管理员', REVIEWER: '审核员', MEMBER: '创作者' })[session.user?.role || 'MEMBER'])
const navigationIcons: Record<string, string> = { '/home': 'home', '/datasets': 'data', '/training': 'train', '/models': 'model', '/releases': 'release', '/reference-imports': 'upload', '/references': 'library', '/system': 'settings', '/publications': 'document', '/reviews': 'review', '/manuscripts': 'document', '/manuscripts/new': 'edit' }
const icon = (to: string) => navigationIcons[to] || (to.includes('grammar') ? 'grammar' : to.includes('image') ? 'image' : 'review')
const group = (to: string) => ['/datasets', '/training', '/models', '/releases'].includes(to) ? '数据与模型' : ['/references', '/reference-imports'].includes(to) ? '历史新闻库' : to === '/system' ? '系统维护' : to === '/home' ? '' : '稿件与审核'
const workspaceLink = (panel: string) => /^\/manuscripts\/\d+\/edit$/.test(route.path) ? `${route.path}?panel=${panel}` : `/workspace/${panel}`
const links = computed(() => [
  { to: '/home', label: '首页' },
  ...(session.user?.role === 'REVIEWER' || session.user?.role === 'ADMIN' ? [{ to: '/datasets', label: '数据中心' }, ...(session.user?.role === 'ADMIN' ? [{ to: '/training', label: '模型训练' }] : []), { to: '/models', label: '模型管理与预测' }, { to: '/releases', label: '模型发布与回退' }, { to: '/reference-imports', label: '批量参考入库' }] : []),
  ...(session.user?.role === 'MEMBER' ? [{ to: '/manuscripts', label: '组织稿件' }, { to: '/manuscripts/new', label: '新建稿件' }] : []),
  ...(session.user?.role === 'MEMBER' ? [{ to: workspaceLink('content'), label: '内容审核' }, { to: workspaceLink('grammar'), label: '语法检查' }, { to: workspaceLink('image'), label: '图文一致性' }] : []),
  ...(session.user?.role === 'REVIEWER' ? [{ to: '/reviews', label: '审核工作台' }] : []),
  ...(session.user?.role === 'ADMIN' ? [{ to: '/references', label: '参考作品' }] : []),
  ...(session.user?.role === 'ADMIN' ? [{ to: '/system', label: '系统管理' }] : []),
  { to: '/publications', label: '已发布' },
])
async function signOut() {
  try { await ElMessageBox.confirm('确认退出当前账号？', '退出登录', { confirmButtonText: '退出', cancelButtonText: '取消' });
    // Run the current page's unsaved-work guard before invalidating its session.
    const navigation=await router.push(session.user?home(session.user.role):'/login')
    if(isNavigationFailure(navigation)&&!isNavigationFailure(navigation,NavigationFailureType.duplicated))return
    await logout(); await router.replace('/login') }
  catch { /* User cancelled or server did not confirm logout; retain current page. */ }
}
</script>
<template>
  <div class="app-shell">
    <a href="#main-content" class="skip-link" @click.prevent="focusMain">跳到主要内容</a>
    <header class="app-header"><button class="navigation-toggle" aria-label="展开或收起导航" :aria-expanded="navigationOpen" @click="navigationOpen = !navigationOpen"><AppIcon name="menu" /></button><RouterLink to="/" class="brand"><img class="school-emblem" :src="'/brand/cucn-emblem.png'" alt="南京传媒学院校徽" /><span class="brand-wording"><img class="school-wordmark" :src="'/brand/cucn-wordmark.png'" alt="南京传媒学院" /><span>校园图文审核工作台</span></span></RouterLink><div class="header-actions">
      <el-popover trigger="click" width="260"><template #reference><el-button>外观</el-button></template>
        <div class="theme-form"><label>显示模式</label><el-select v-model="theme.mode" @change="applyTheme(theme)"><el-option label="浅色" value="light" /><el-option label="深色" value="dark" /><el-option label="跟随系统" value="system" /></el-select><label>主题色</label><div class="theme-colors"><button v-for="color in ['#215dba', '#16704a', '#7955a3', '#a34131']" :key="color" :aria-label="`使用主题色 ${color}`" :style="{ background: color }" @click="theme.primary = color; applyTheme(theme)" /><input v-model="theme.primary" aria-label="自定义主题色" type="color" @input="applyTheme(theme)" /></div></div>
      </el-popover><span class="account-label">{{ session.user?.displayName }}<small>{{ roleName }}</small></span><el-button @click="signOut">退出</el-button>
    </div></header>
    <div class="shell-body"><button v-if="navigationOpen" class="navigation-scrim" aria-label="关闭导航" @click="navigationOpen = false" /><aside class="sidebar" :class="{ 'navigation-open': navigationOpen }"><div class="organization-label"><span>当前工作空间</span><strong>{{ session.user?.organizations.map(o => o.name).join(' / ') || '南京传媒学院 · 全校' }}</strong></div><nav aria-label="主导航"><template v-for="(link,index) in links" :key="link.to"><span v-if="group(link.to) && (index === 0 || group(link.to) !== group(links[index-1]!.to))" class="nav-group">{{ group(link.to) }}</span><RouterLink :to="contextualLink(link.to)" :active-class="link.to.includes('?panel=') ? 'workspace-route' : 'router-link-active'" :class="{ 'workspace-active': link.to === `${route.path}?panel=${String(route.query.panel || 'content')}` }"><AppIcon :name="icon(link.to)" /><span>{{ link.label }}</span></RouterLink></template></nav><div class="sidebar-foot">校园内容 · 有序流转</div></aside>
      <main id="main-content" class="page-content" tabindex="-1"><div class="page-heading"><div><span class="page-eyebrow">{{ roleName }}工作台 / 南京传媒学院</span><h1>{{ route.meta.title }}</h1></div><span class="page-heading-mark" aria-hidden="true"><AppIcon :name="icon(route.path)" :size="28" /></span></div><WorkflowNavigator /><RouterView :key="route.path" /></main>
    </div>
  </div>
</template>
