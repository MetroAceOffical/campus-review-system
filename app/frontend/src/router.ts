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
      { path: 'home', component: () => import('./views/HomeView.vue'), meta: { title: '首页' } },
      { path: 'system', component: () => import('./views/SystemView.vue'), meta: { title: '系统管理', role: 'ADMIN' } },
      { path: 'datasets', component: () => import('./views/DatasetView.vue'), meta: { title: '数据中心', roles: ['REVIEWER', 'ADMIN'] } },
      { path: 'training', component: () => import('./views/TrainingView.vue'), meta: { title: '模型训练', role: 'ADMIN' } },
      { path: 'models', component: () => import('./views/ModelView.vue'), meta: { title: '模型管理与预测', roles: ['REVIEWER', 'ADMIN'] } },
      { path: 'releases', component: () => import('./views/ReleaseView.vue'), meta: { title: '模型发布与回退', roles: ['REVIEWER', 'ADMIN'] } },
      { path: 'reference-imports', component: () => import('./views/ReferenceImportView.vue'), meta: { title: '批量参考入库', roles: ['REVIEWER', 'ADMIN'] } },
      { path: 'manuscripts', component: () => import('./views/ManuscriptListView.vue'), meta: { title: '组织稿件', role: 'MEMBER' } },
      { path: 'manuscripts/:id/history', component: () => import('./views/SubmissionHistoryView.vue'), meta: { title: '版本与处理状态', role: 'MEMBER' } },
      { path: 'manuscripts/new', name: 'new-manuscript', component: EditorView, meta: { title: '编辑稿件', role: 'MEMBER' } },
      { path: 'workspace/:panel', component: () => import('./views/WorkspaceGateway.vue'), meta: { title: '稿件检查工作区', role: 'MEMBER' } },
      { path: 'manuscripts/:id/edit', component: EditorView, meta: { title: '编辑稿件', role: 'MEMBER' } },
      { path: 'reviews', component: () => import('./views/ReviewQueueView.vue'), meta: { title: '审核工作台', role: 'REVIEWER' } },
      { path: 'reviews/:id', component: () => import('./views/ReviewDetailView.vue'), meta: { title: '稿件审核', role: 'REVIEWER' } },
      { path: 'experiments', redirect: '/models' },
      { path: 'references', component: () => import('./views/ReferenceListView.vue'), meta: { title: '参考作品', role: 'ADMIN' } },
      { path: 'references/new', component: () => import('./views/ReferenceEditorView.vue'), meta: { title: '添加参考作品', role: 'ADMIN' } },
      { path: 'publications', component: () => import('./views/PublicationListView.vue'), meta: { title: '已发布' } },
      { path: 'sources/:id', component: () => import('./views/SourceView.vue'), meta: { title: '引用来源版本' } },
      { path: 'publications/:id', component: () => import('./views/PublicationDetailView.vue'), meta: { title: '发布内容' } },
    ] },
  ],
})
router.beforeEach(async (to,from) => {
  if (from.query.flow && to.query.flow===undefined && ['/datasets','/training','/models','/releases','/reference-imports','/references'].includes(to.path)) return {path:to.path,query:{...to.query,flow:from.query.flow},hash:to.hash}
  if (!session.loaded) await loadSession()
  if (!session.user && to.path !== '/login') return '/login'
  if (session.user && (to.path === '/' || to.path === '/login' || (to.meta.role && to.meta.role !== session.user.role) || (Array.isArray(to.meta.roles) && !to.meta.roles.includes(session.user.role)))) return home(session.user.role)
})
