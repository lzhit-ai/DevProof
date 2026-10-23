import { computed, ref } from 'vue'

export interface ProjectContextItem {
  id: string
  name: string
  description: string | null
  version: number
  created_at: string
  can_delete: boolean
}

export interface CurrentUser {
  id: string
  display_name: string
  email: string
}

const projectStorageKey = 'workbenchProjectId'
let projectLoadVersion = 0

export const projects = ref<ProjectContextItem[]>([])
export const selectedProjectId = ref(sessionStorage.getItem(projectStorageKey) ?? '')
export const projectContextLoading = ref(false)
export const projectContextError = ref('')
export const projectContextNotice = ref('')
export const currentUser = ref<CurrentUser | null>(null)
export const currentUserLoading = ref(false)
export const selectedProject = computed(() => projects.value.find((project) => project.id === selectedProjectId.value) ?? null)

export function projectHeaders(write = false): HeadersInit {
  const headers: Record<string, string> = { Authorization: `Bearer ${sessionStorage.getItem('accessToken') ?? ''}` }
  if (write) {
    headers['Content-Type'] = 'application/json'
    headers['Idempotency-Key'] = crypto.randomUUID()
  }
  return headers
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  const body = await response.json().catch(() => ({}))
  if (response.status === 401) {
    handleSessionExpired()
  }
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : body.detail?.message
    throw new Error(body.message ?? detail ?? `请求失败 (${response.status})`)
  }
  return body as T
}

/** Token 过期或无效:清除会话状态并回到登录页。 */
function handleSessionExpired() {
  sessionStorage.removeItem('accessToken')
  sessionStorage.removeItem(projectStorageKey)
  if (window.location.pathname !== '/login') {
    window.location.assign('/login')
  }
}

export function selectProject(projectId: string) {
  projectContextNotice.value = ''
  selectedProjectId.value = projectId
  if (projectId) sessionStorage.setItem(projectStorageKey, projectId)
  else sessionStorage.removeItem(projectStorageKey)
}

export async function loadProjects() {
  if (!sessionStorage.getItem('accessToken')) return
  const loadVersion = ++projectLoadVersion
  projectContextLoading.value = true
  projectContextError.value = ''
  try {
    const loaded = await apiRequest<ProjectContextItem[]>('/projects', { headers: projectHeaders() })
    if (loadVersion !== projectLoadVersion) return
    projects.value = loaded
    if (!projects.value.some((project) => project.id === selectedProjectId.value)) {
      selectProject(projects.value[0]?.id ?? '')
    }
  } catch (error) {
    if (loadVersion !== projectLoadVersion) return
    projectContextError.value = error instanceof Error ? error.message : '项目列表加载失败'
    projects.value = []
    selectProject('')
  } finally {
    if (loadVersion === projectLoadVersion) projectContextLoading.value = false
  }
}

export async function loadCurrentUser() {
  if (!sessionStorage.getItem('accessToken')) return
  currentUserLoading.value = true
  try {
    currentUser.value = await apiRequest<CurrentUser>('/auth/me', { headers: projectHeaders() })
  } catch {
    currentUser.value = null
  } finally {
    currentUserLoading.value = false
  }
}

export async function createProject(name: string, description = '', repositoryUrl = '', knowledgeBaseIds: string[] = []): Promise<ProjectContextItem> {
  const project = await apiRequest<ProjectContextItem>('/projects', {
    method: 'POST',
    headers: projectHeaders(true),
    body: JSON.stringify({ name, description: description || null, repository_url: repositoryUrl || null, knowledge_base_ids: knowledgeBaseIds }),
  })
  ++projectLoadVersion
  projectContextLoading.value = false
  projects.value = [project, ...projects.value]
  selectProject(project.id)
  return project
}

export async function deleteProject(projectId: string, confirmationName: string): Promise<void> {
  await apiRequest<void>(`/projects/${projectId}`, {
    method: 'DELETE',
    headers: projectHeaders(true),
    body: JSON.stringify({ confirmation_name: confirmationName }),
  })
  // A list request started before this deletion must not restore the project.
  ++projectLoadVersion
  projectContextLoading.value = false
  projectContextError.value = ''
  projects.value = projects.value.filter((project) => project.id !== projectId)
  if (selectedProjectId.value === projectId) selectProject(projects.value[0]?.id ?? '')
  projectContextNotice.value = `项目「${confirmationName}」已删除。`
}

export function resetProjectContext() {
  ++projectLoadVersion
  projectContextLoading.value = false
  projects.value = []
  projectContextError.value = ''
  selectProject('')
}

export function resetCurrentUser() {
  currentUser.value = null
  currentUserLoading.value = false
}
