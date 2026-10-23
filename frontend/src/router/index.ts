import { createRouter, createWebHistory } from 'vue-router'
import WorkbenchLayout from '../layouts/WorkbenchLayout.vue'
import ApprovalDetailPage from '../pages/ApprovalDetailPage.vue'
import AgentBlocksPage from '../pages/AgentBlocksPage.vue'
import ApprovalQueuePage from '../pages/ApprovalQueuePage.vue'
import DeliveryDetailPage from '../pages/DeliveryDetailPage.vue'
import DeliveryHistoryPage from '../pages/DeliveryHistoryPage.vue'
import IntegrationsSettingsPage from '../pages/IntegrationsSettingsPage.vue'
import KnowledgeBasePage from '../pages/KnowledgeBasePage.vue'
import LoginPage from '../pages/LoginPage.vue'
import NotebookWorkspacePage from '../pages/NotebookWorkspacePage.vue'
import ProjectStatusPage from '../pages/ProjectStatusPage.vue'
import PlanningPage from '../pages/PlanningPage.vue'
import SecurityBaselinePage from '../pages/SecurityBaselinePage.vue'
import TaskCenterPage from '../pages/TaskCenterPage.vue'
import WorkbenchHomePage from '../pages/WorkbenchHomePage.vue'

function hasToken(): boolean {
  return Boolean(sessionStorage.getItem('accessToken'))
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      component: LoginPage,
      meta: { guest: true },
    },
    {
      path: '/register',
      component: LoginPage,
      meta: { guest: true },
    },
    {
      path: '/',
      component: WorkbenchLayout,
      children: [
        { path: '', redirect: '/workbench' },
        { path: 'workbench', component: WorkbenchHomePage, meta: { title: '工作台', area: 'project' } },
        { path: 'planning', component: PlanningPage, meta: { title: '需求规划', area: 'project' } },
        { path: 'knowledge-base', component: KnowledgeBasePage, meta: { title: '项目知识库', area: 'project' } },
        { path: 'agent-blocks', component: AgentBlocksPage, meta: { title: 'Agent 功能块', area: 'project' } },
        { path: 'tasks', component: TaskCenterPage, meta: { title: '代码交付', area: 'project' } },
        { path: 'tasks/:taskId/notebook', component: NotebookWorkspacePage, meta: { title: 'Notebook 审查', area: 'project', section: 'notebook' } },
        { path: 'approvals', component: ApprovalQueuePage, meta: { title: '待审批队列', area: 'approval' } },
        { path: 'approvals/:approvalId', component: ApprovalDetailPage, meta: { title: '审批详情', area: 'approval' } },
        { path: 'project-status', component: ProjectStatusPage, meta: { title: '项目态势', area: 'project' } },
        { path: 'security-baselines', component: SecurityBaselinePage, meta: { title: '安全与质量', area: 'project' } },
        { path: 'deliveries', component: DeliveryHistoryPage, meta: { title: '正式记录', area: 'project' } },
        { path: 'deliveries/:deliveryId', component: DeliveryDetailPage, meta: { title: '交付详情', area: 'project' } },
        { path: 'settings', component: IntegrationsSettingsPage, meta: { title: '集成与设置', area: 'settings' } },
      ],
    },
  ],
})

router.beforeEach((to) => {
  if (to.meta.guest) return true
  if (!hasToken()) return '/login'
  return true
})
