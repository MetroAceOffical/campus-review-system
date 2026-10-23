import { createRouter, createWebHashHistory } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'
import LoginView from './views/LoginView.vue'
import { home, loadSession, session } from './session'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: AppLayout, children: [
      { path: 'manuscripts', component: { render: () => null }, meta: { title: '组织稿件', role: 'MEMBER' } },
      { path: 'reviews', component: { render: () => null }, meta: { title: '审核工作台', role: 'REVIEWER' } },
      { path: 'experiments', component: { render: () => null }, meta: { title: '模型实验', role: 'ADMIN' } },
      { path: 'references', component: { render: () => null }, meta: { title: '参考作品', role: 'ADMIN' } },
      { path: 'publications', component: { render: () => null }, meta: { title: '已发布' } },
    ] },
  ],
})
router.beforeEach(async to => {
  if (!session.loaded) await loadSession()
  if (!session.user && to.path !== '/login') return '/login'
  if (session.user && (to.path === '/' || to.path === '/login' || (to.meta.role && to.meta.role !== session.user.role))) return home(session.user.role)
})
