import { createRouter, createWebHashHistory } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'
import LoginView from './views/LoginView.vue'
import EditorView from './views/EditorView.vue'
import { home, loadSession, session } from './session'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: AppLayout, children: [
      { path: 'datasets', component: () => import('./views/DatasetView.vue'), meta: { title: '数据中心', roles: ['MEMBER', 'ADMIN'] } },
      { path: 'training', component: () => import('./views/TrainingView.vue'), meta: { title: '模型训练', roles: ['MEMBER', 'ADMIN'] } },
      { path: 'models', component: () => import('./views/ModelView.vue'), meta: { title: '模型管理与预测', roles: ['MEMBER', 'ADMIN'] } },
      { path: 'manuscripts', component: () => import('./views/ManuscriptListView.vue'), meta: { title: '组织稿件', role: 'MEMBER' } },
      { path: 'manuscripts/:id/history', component: () => import('./views/SubmissionHistoryView.vue'), meta: { title: '版本与处理状态', role: 'MEMBER' } },
      { path: 'manuscripts/new', name: 'new-manuscript', component: EditorView, meta: { title: '编辑稿件', role: 'MEMBER' } },
      { path: 'manuscripts/:id/edit', component: EditorView, meta: { title: '编辑稿件', role: 'MEMBER' } },
      { path: 'reviews', component: () => import('./views/ReviewQueueView.vue'), meta: { title: '审核工作台', role: 'REVIEWER' } },
      { path: 'reviews/:id', component: () => import('./views/ReviewDetailView.vue'), meta: { title: '稿件审核', role: 'REVIEWER' } },
      { path: 'experiments', redirect: '/models' },
      { path: 'references', component: () => import('./views/ReferenceListView.vue'), meta: { title: '参考作品', role: 'ADMIN' } },
      { path: 'references/new', component: () => import('./views/ReferenceEditorView.vue'), meta: { title: '添加参考作品', role: 'ADMIN' } },
      { path: 'publications', component: () => import('./views/PublicationListView.vue'), meta: { title: '已发布' } },
      { path: 'publications/:id', component: () => import('./views/PublicationDetailView.vue'), meta: { title: '发布内容' } },
    ] },
  ],
})
router.beforeEach(async to => {
  if (!session.loaded) await loadSession()
  if (!session.user && to.path !== '/login') return '/login'
  if (session.user && (to.path === '/' || to.path === '/login' || (to.meta.role && to.meta.role !== session.user.role) || (Array.isArray(to.meta.roles) && !to.meta.roles.includes(session.user.role)))) return home(session.user.role)
})
