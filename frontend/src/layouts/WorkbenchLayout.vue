<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { currentUser, currentUserLoading, loadCurrentUser, loadProjects, projectContextLoading, projectContextNotice, projects, resetCurrentUser, selectProject, selectedProject, selectedProjectId, createProject, apiRequest, projectHeaders } from '../features/projects/project-context'

interface KnowledgeBaseOption { id: string; name: string; project_id: string }

const route = useRoute()
const router = useRouter()
const navigationItems = [
  { label: '工作台', to: '/workbench', icon: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z' },
  { label: '需求规划', to: '/planning', icon: 'M8 4h8v4H8zM8 6H5v15h14V6h-3M8 12h8m-8 4h5' },
  { label: '代码交付', to: '/tasks', icon: 'm8 5-7 7 7 7m8-14 7 7-7 7M14 3l-4 18' },
  { label: '知识库', to: '/knowledge-base', icon: 'M12 5v16M3 3h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v16h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3Z' },
  { label: '审批', to: '/approvals', icon: 'M9 3h6v4H9zM9 5H5v16h14V5h-4m-7 9 3 3 5-6' },
  { label: '交付记录', to: '/deliveries', icon: 'M5 3h10l4 4v14H5ZM14 3v5h5M8 12h8m-8 4h6' },
  { label: '设置', to: '/settings', icon: 'M4 7h16M4 17h16M9 4v6m6 4v6' },
]
const title = computed(() => String(route.meta.title ?? 'DevProof'))
const currentUserInitial = computed(() => currentUser.value?.display_name.trim().slice(0, 1) || '…')
const currentUserName = computed(() => currentUser.value?.display_name || (currentUserLoading.value ? '正在读取账号' : '账号信息不可用'))
const currentUserEmail = computed(() => currentUser.value?.email || (currentUserLoading.value ? '请稍候' : '请重新登录'))
const showProjectOnboarding = ref(false)
const onboardingForm = ref({ name: '', description: '', repositoryUrl: '' })
const onboardingBusy = ref(false)
const onboardingStep = ref('')
const onboardingMessage = ref('')
const requiresProjectContext = computed(() => route.path !== '/workbench' && !projectContextLoading.value && !selectedProject.value)
const kbPickerOpen = ref(false)
const kbOptions = ref<KnowledgeBaseOption[]>([])
const selectedKbIds = ref<string[]>([])
const kbPickerLoading = ref(false)
const projectNoticeVisible = ref(false)
let projectNoticeTimer: ReturnType<typeof setTimeout> | undefined

function dismissProjectNotice() {
  if (!projectNoticeVisible.value) return
  window.clearTimeout(projectNoticeTimer)
  projectNoticeVisible.value = false
}

function clearProjectNotice() {
  projectContextNotice.value = ''
}

watch(projectContextNotice, (notice) => {
  window.clearTimeout(projectNoticeTimer)
  projectNoticeVisible.value = Boolean(notice)
  if (notice) projectNoticeTimer = window.setTimeout(dismissProjectNotice, 2000)
})

function logout() {
  sessionStorage.removeItem('accessToken')
  sessionStorage.removeItem('loginEmail')
  resetCurrentUser()
  router.replace('/login')
}

function changeProject(event: Event) {
  selectProject((event.target as HTMLSelectElement).value)
}

function resetOnboarding() {
  onboardingForm.value = { name: '', description: '', repositoryUrl: '' }
  onboardingMessage.value = ''
  onboardingStep.value = ''
  selectedKbIds.value = []
}

function openProjectCreate() {
  onboardingMessage.value = ''
  showProjectOnboarding.value = true
}

function closeProjectCreate() {
  if (onboardingBusy.value) return
  showProjectOnboarding.value = false
  resetOnboarding()
}

async function openKbPicker() {
  kbPickerLoading.value = true
  try {
    kbOptions.value = await apiRequest<KnowledgeBaseOption[]>('/knowledge-bases', { headers: projectHeaders() })
  } catch (e) {
    onboardingMessage.value = e instanceof Error ? e.message : '知识库列表加载失败'
  } finally {
    kbPickerLoading.value = false
  }
  kbPickerOpen.value = true
}

function toggleKb(id: string) {
  selectedKbIds.value = selectedKbIds.value.includes(id)
    ? selectedKbIds.value.filter((item) => item !== id)
    : [...selectedKbIds.value, id]
}

provide('openProjectCreate', openProjectCreate)

async function submitProjectOnboarding() {
  const name = onboardingForm.value.name.trim()
  if (!name) return
  const repositoryUrl = onboardingForm.value.repositoryUrl.trim()
  if (!repositoryUrl) {
    onboardingMessage.value = '请填写 GitHub 仓库地址。'
    return
  }

  onboardingBusy.value = true
  onboardingMessage.value = ''
  onboardingStep.value = '正在创建项目'
  try {
    // One request creates the project and registers + queues a GitHub source
    // sync in a single transaction; the actual PR sync runs in the background.
    await createProject(name, onboardingForm.value.description.trim(), repositoryUrl, selectedKbIds.value)
    showProjectOnboarding.value = false
    resetOnboarding()
    await router.push('/tasks')
  } catch (error) {
    onboardingMessage.value = `创建项目失败：${error instanceof Error ? error.message : '未知错误'}。请修正后重试。`
  } finally {
    onboardingBusy.value = false
  }
}

onMounted(() => { void loadProjects(); void loadCurrentUser() })
onBeforeUnmount(() => window.clearTimeout(projectNoticeTimer))
</script>

<template>
  <div class="workbench-shell">
    <aside class="global-nav" aria-label="主导航">
      <RouterLink class="brand-lockup" to="/workbench" aria-label="DevProof 主页"><img class="brand-symbol" src="/project-icon.svg" alt="" width="28" height="28" /><strong>DevProof</strong></RouterLink>
      <nav class="primary-navigation"><RouterLink v-for="item in navigationItems" :key="item.to" class="nav-item" :to="item.to"><svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="item.icon" /></svg><span>{{ item.label }}</span></RouterLink></nav>
      <div class="demo-user-card" :aria-label="`当前用户：${currentUserName}，${currentUserEmail}`"><span class="demo-user-avatar" aria-hidden="true">{{ currentUserInitial }}</span><span class="demo-user-copy"><strong>{{ currentUserName }}</strong><small>{{ currentUserEmail }}</small></span></div>
    </aside>
    <div class="workbench-content">
      <header class="global-topbar">
        <div class="topbar-page-title"><h1>{{ title }}</h1></div>
        <div class="topbar-project-actions"><label class="project-switch"><span>项目</span><select :value="selectedProjectId" :disabled="projectContextLoading" aria-label="选择当前项目" @change="changeProject"><option v-if="projectContextLoading" value="">加载项目中…</option><option v-else-if="!projects.length" value="">暂无项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label><button class="topbar-create-project" type="button" @click="openProjectCreate">新建项目</button></div>

        <div class="topbar-actions"><button type="button" @click="logout" aria-label="退出登录">退出</button></div>
      </header>
      <div v-if="showProjectOnboarding" class="project-onboarding-overlay" @click.self="closeProjectCreate">
        <section class="project-onboarding" aria-label="创建并接入项目" role="dialog" aria-modal="true">
          <form class="project-onboarding-form" @submit.prevent="submitProjectOnboarding">
            <div class="project-onboarding-copy"><h2>创建并接入项目</h2><p>填写项目名称和 GitHub 仓库地址。</p></div>
            <label>项目名称<input v-model="onboardingForm.name" maxlength="200" required autofocus placeholder="例如：支付平台重构" /></label>
            <label>项目说明（可选）<input v-model="onboardingForm.description" maxlength="4000" placeholder="用来区分这次开发工作的范围" /></label>
            <label class="project-onboarding-repository">GitHub 仓库地址<input v-model="onboardingForm.repositoryUrl" required placeholder="https://github.com/owner/repository" /></label>
            <div class="project-onboarding-kb">
              <span>关联知识库（可选）</span>
              <button type="button" class="kb-pick-button" @click="openKbPicker">＋ 选择知识库</button>
            </div>
            <div v-if="selectedKbIds.length" class="project-onboarding-kb-list">
              <span v-for="id in selectedKbIds" :key="id" class="project-onboarding-kb-chip">
                {{ kbOptions.find((o) => o.id === id)?.name ?? '知识库' }}
                <button type="button" aria-label="移除" @click="toggleKb(id)">×</button>
              </span>
            </div>
            <div class="project-onboarding-actions"><button class="primary-button" type="submit" :disabled="onboardingBusy || !onboardingForm.name.trim() || !onboardingForm.repositoryUrl.trim()">{{ onboardingBusy ? onboardingStep : '创建项目' }}</button><button type="button" :disabled="onboardingBusy" @click="closeProjectCreate">取消</button></div>
          </form>

          <!-- 知识库选择子弹窗 -->
          <div v-if="kbPickerOpen" class="project-onboarding-overlay" @click.self="kbPickerOpen = false">
            <section class="project-onboarding project-kb-picker" role="dialog" aria-modal="true">
              <div class="project-onboarding-copy"><h2>选择知识库</h2><p>勾选要挂载到该项目的知识库。</p></div>
              <div v-if="kbPickerLoading" class="project-onboarding-note">加载中…</div>
              <div v-else-if="!kbOptions.length" class="project-onboarding-note">暂无可用知识库，可先去知识库页创建。</div>
              <ul v-else class="project-kb-list">
                <li v-for="kb in kbOptions" :key="kb.id">
                  <label>
                    <input type="checkbox" :checked="selectedKbIds.includes(kb.id)" @change="toggleKb(kb.id)" />
                    <span>{{ kb.name }}</span>
                  </label>
                </li>
              </ul>
              <div class="project-onboarding-actions">
                <button type="button" class="primary-button" @click="kbPickerOpen = false">完成</button>
              </div>
            </section>
          </div>

          <p v-if="onboardingMessage" class="project-create-error" role="alert">{{ onboardingMessage }}</p>
        </section>
      </div>
      <main class="workbench-main" :aria-label="title">
        <section v-if="requiresProjectContext" class="project-context-empty"><div><h2>{{ projects.length ? '先选择一个项目' : '先创建并接入一个项目' }}</h2><p>{{ projects.length ? '代码交付、资料、审批和交付记录都属于某个项目。请从顶部选择项目，或创建并接入一个新项目。' : '先接入 GitHub 仓库并同步 Pull Request。完成后，即可从一次代码交付开始审查。' }}</p><button class="primary-button" type="button" @click="openProjectCreate">创建并接入项目</button></div></section>
        <RouterView v-else />
      </main>
    </div>
    <Teleport to="body">
      <Transition name="project-operation-toast" @after-leave="clearProjectNotice">
        <aside v-if="projectNoticeVisible" class="project-operation-notice" role="status" aria-live="polite" @pointerenter="dismissProjectNotice">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4.2 4L19 6.5" /></svg>
          <span>{{ projectContextNotice }}</span>
        </aside>
      </Transition>
    </Teleport>
  </div>
</template>
