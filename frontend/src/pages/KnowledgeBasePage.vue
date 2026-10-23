<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import {
  apiRequest,
  projectHeaders,
  selectedProjectId,
} from '../features/projects/project-context'

interface KnowledgeBase {
  id: string
  project_id: string
  name: string
  created_at: string
  updated_at: string
}

interface SourceDoc {
  id: string
  project_id: string
  logical_name: string
  source_role: string
  revision_no: number
  media_type: string
  original_filename: string
  processing_status: string
  parser_version: string | null
  failure_code: string | null
  ingestion_job_status: string | null
  knowledge_base_id: string | null
  force_ocr: boolean
  created_at: string
  updated_at: string
}

const knowledgeBases = ref<KnowledgeBase[]>([])
const sources = ref<SourceDoc[]>([])
const loading = ref(false)
const error = ref('')
const selectedKbId = ref<string | null>(null)
const selectedDocId = ref<string | null>(null)

interface ChunkItem {
  id: string
  chunk_index: number
  content: string
  locator: Record<string, unknown>
  index_version: string
}

const viewerTab = ref<'content' | 'chunks'>('content')
const docContent = ref('')
const docChunks = ref<ChunkItem[]>([])
const viewerLoading = ref(false)
const viewerError = ref('')

/** full Markdown, rendered to safe HTML once (marked + DOMPurify) */
const renderedContent = computed(() =>
  DOMPurify.sanitize(marked.parse(docContent.value ?? '') as string),
)

function locatorText(locator: Record<string, unknown>) {
  const entries = Object.entries(locator)
  if (!entries.length) return ''
  const [key, value] = entries[0]
  const label = ({ paragraph: '段落', line: '行', charStart: '字符', section: '小节' } as Record<string, string>)[key] ?? key
  return `${label} ${value}`
}

async function loadDoc(docId: string) {
  viewerTab.value = 'content'
  viewerLoading.value = true
  viewerError.value = ''
  const projectId = selectedProjectId.value
  if (!projectId) return
  try {
    const [content, chunks] = await Promise.all([
      apiRequest<{ content: string }>(`/projects/${projectId}/sources/${docId}`, { headers: projectHeaders() }),
      apiRequest<ChunkItem[]>(`/projects/${projectId}/sources/${docId}/chunks`, { headers: projectHeaders() }),
    ])
    docContent.value = content.content
    docChunks.value = chunks
  } catch (err) {
    viewerError.value = err instanceof Error ? err.message : '文档内容加载失败'
  } finally {
    viewerLoading.value = false
  }
}

function closeViewer() {
  selectedDocId.value = null
}

const expandedKbs = ref<Set<string>>(new Set())

const uploadModal = ref<{ file: File } | null>(null)
const uploadTargetKbId = ref<string | null>(null)
const uploadForceOcr = ref(true)
const createKbModal = ref(false)
const createKbName = ref('')
const mountKbModal = ref(false)
const mountableKbs = ref<KnowledgeBase[]>([])
const mountKbLoading = ref(false)
const uploading = ref(false)

async function loadKnowledgeBase() {
  const projectId = selectedProjectId.value
  if (!projectId) {
    error.value = '请先在顶部选择项目'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [kbList, sourceList] = await Promise.all([
      apiRequest<KnowledgeBase[]>(`/projects/${projectId}/knowledge-bases`, { headers: projectHeaders() }),
      apiRequest<SourceDoc[]>(`/projects/${projectId}/sources`, { headers: projectHeaders() }),
    ])
    knowledgeBases.value = kbList
    sources.value = sourceList
  } catch (err) {
    error.value = err instanceof Error ? err.message : '知识库加载失败'
  } finally {
    loading.value = false
    reconcilePolling()
  }
}

function docsInKb(kbId: string | null): SourceDoc[] {
  return sources.value.filter((source) => source.knowledge_base_id === kbId)
}

/** 判断一个知识库是否展开 */
function isExpanded(kbId: string) {
  return expandedKbs.value.has(kbId)
}

function selectKb(id: string) {
  selectedKbId.value = id
  selectedDocId.value = null
  expandedKbs.value.add(id)
}

function selectDoc(id: string) {
  selectedDocId.value = id
  selectedKbId.value = null
  loadDoc(id)
}

const activeKb = computed(() => knowledgeBases.value.find((kb) => kb.id === selectedKbId.value) ?? null)
const activeDoc = computed(() => sources.value.find((source) => source.id === selectedDocId.value) ?? null)

function extOf(name: string) {
  const match = name.match(/\.(\w+)$/)
  return (match?.[1] ?? 'PDF').toUpperCase()
}

const statusBadge: Record<string, string> = {
  UPLOADED: '待处理',
  PARSING: '处理中',
  OCR_CHECKING: '处理中',
  CHUNKING: '处理中',
  INDEXING: '处理中',
  READY: '已完成',
  FAILED: '失败',
}

function statusText(status: string) {
  return statusBadge[status] ?? status
}

function openUploadDialog() {
  const input = document.createElement('input')
  input.type = 'file'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) {
      uploadTargetKbId.value = selectedKbId.value
      uploadForceOcr.value = true
      uploadModal.value = { file }
    }
  }
  input.click()
}

async function confirmUpload() {
  if (!uploadModal.value || uploading.value) return
  const file = uploadModal.value.file
  const projectId = selectedProjectId.value
  if (!projectId) return
  uploading.value = true
  error.value = ''
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('source_role', '知识库')
    formData.append('logical_name', file.name)
    if (uploadTargetKbId.value) formData.append('knowledge_base_id', uploadTargetKbId.value)
    formData.append('force_ocr', uploadForceOcr.value ? 'true' : 'false')
    await apiRequest(`/projects/${projectId}/sources`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${sessionStorage.getItem('accessToken') ?? ''}`,
        'Idempotency-Key': crypto.randomUUID(),
      },
      body: formData,
    })
    await loadKnowledgeBase()
    uploadModal.value = null
  } catch (err) {
    error.value = err instanceof Error ? err.message : `上传失败 (${file.name})`
  } finally {
    uploading.value = false
  }
}

async function confirmCreateKb() {
  const projectId = selectedProjectId.value
  if (!projectId) return
  const name = createKbName.value.trim()
  if (!name) return
  try {
    await apiRequest(`/projects/${projectId}/knowledge-bases`, {
      method: 'POST',
      headers: projectHeaders(true),
      body: JSON.stringify({ name }),
    })
    createKbName.value = ''
    createKbModal.value = false
    await loadKnowledgeBase()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建知识库失败'
  }
}

async function openMountPicker() {
  const projectId = selectedProjectId.value
  if (!projectId) return
  mountKbLoading.value = true
  try {
    const [allKbs, mountedKbs] = await Promise.all([
      apiRequest<KnowledgeBase[]>('/knowledge-bases', { headers: projectHeaders() }),
      apiRequest<KnowledgeBase[]>(`/projects/${projectId}/knowledge-bases`, { headers: projectHeaders() }),
    ])
    const mountedIds = new Set(mountedKbs.map((kb) => kb.id))
    mountableKbs.value = allKbs.filter((kb) => !mountedIds.has(kb.id))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '知识库列表加载失败'
  } finally {
    mountKbLoading.value = false
  }
  mountKbModal.value = true
}

async function confirmMountKb(kb: KnowledgeBase) {
  const projectId = selectedProjectId.value
  if (!projectId) return
  try {
    await apiRequest(`/projects/${projectId}/knowledge-bases/mount`, {
      method: 'POST',
      headers: projectHeaders(true),
      body: JSON.stringify({ knowledge_base_id: kb.id }),
    })
    mountKbModal.value = false
    await loadKnowledgeBase()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '挂载知识库失败'
  }
}

async function deleteDoc(doc: SourceDoc) {
  const projectId = selectedProjectId.value
  if (!projectId) return
  if (!confirm(`确定删除「${doc.logical_name}」？`)) return
  try {
    await apiRequest(`/projects/${projectId}/sources/${doc.id}`, {
      method: 'DELETE',
      headers: projectHeaders(true),
    })
    if (selectedDocId.value === doc.id) selectedDocId.value = null
    await loadKnowledgeBase()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '删除失败'
  }
}

async function unmountKb(kb: KnowledgeBase) {
  const projectId = selectedProjectId.value
  if (!projectId) return
  const isOwn = kb.project_id === projectId
  if (!confirm(`确定${isOwn ? '删除知识库' : '解除挂载知识库'}「${kb.name}」？${isOwn ? '该知识库下的文档也会删除。' : '仅解除与本项目的挂载，不影响知识库本身。'}`)) return
  try {
    await apiRequest(`/projects/${projectId}/knowledge-bases/${kb.id}`, {
      method: 'DELETE',
      headers: projectHeaders(true),
    })
    if (selectedKbId.value === kb.id) selectedKbId.value = null
    await loadKnowledgeBase()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '操作失败'
  }
}

// 智能轮询:只要存在「处理中」的文档就每隔几秒自动刷新,全部到达终态后自动停止。
const POLL_INTERVAL_MS = 4000
const PENDING_STATUSES = new Set(['UPLOADED', 'PARSING', 'OCR_CHECKING', 'CHUNKING', 'INDEXING'])
let pollTimer: number | null = null

function hasPendingDocument(): boolean {
  return sources.value.some((source) => PENDING_STATUSES.has(source.processing_status))
}

function reconcilePolling() {
  if (hasPendingDocument()) {
    if (pollTimer === null) {
      pollTimer = window.setInterval(async () => {
        await loadKnowledgeBase()
      }, POLL_INTERVAL_MS)
    }
  } else if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

onBeforeUnmount(() => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
})

onMounted(loadKnowledgeBase)
</script>

<template>
  <section class="page page-knowledge">
    <header class="page-heading">
      <div><h1>项目知识库</h1></div>
      <button v-if="error" class="kb-retry" type="button" @click="loadKnowledgeBase">重试</button>
    </header>

    <div v-if="error && !loading" class="kb-error">{{ error }}</div>

    <div class="kb-layout">
      <!-- 左侧：知识库列表 -->
      <aside class="kb-sidebar">
        <div class="kb-sidebar-actions">
          <button class="kb-create" type="button" @click="createKbModal = true">＋ 创建知识库</button>
          <button class="kb-mount" type="button" @click="openMountPicker">挂载知识库</button>
        </div>
        <div class="kb-tree-label">已挂载知识库</div>
        <nav class="kb-tree">
          <div v-for="kb in knowledgeBases" :key="kb.id" class="kb-node">
            <button class="kb-node-row" :class="{ active: selectedKbId === kb.id && !selectedDocId }" type="button" @click="selectKb(kb.id)">
              <span :class="['kb-caret', !isExpanded(kb.id) ? 'collapsed' : '']">▾</span>
              <i class="kb-folder-ico plain">▤</i>
              <span class="kb-node-name">{{ kb.name }}</span>
              <button class="kb-del-mini" type="button" @click.stop="unmountKb(kb)">×</button>
            </button>
            <div v-if="isExpanded(kb.id)" class="kb-node-children">
              <button
                v-for="doc in docsInKb(kb.id)"
                :key="doc.id"
                class="kb-node-row kb-node-doc"
                :class="{ active: selectedDocId === doc.id }"
                type="button"
                @click="selectDoc(doc.id)"
              >
                <i class="kb-doc-dot">{{ extOf(doc.logical_name) }}</i>
                <span class="kb-node-name">{{ doc.logical_name }}</span>
              </button>
            </div>
          </div>
          <!-- 未分组（未挂到任何知识库）文档 -->
          <div v-if="docsInKb(null).length" class="kb-tree-label">未分组文档</div>
          <button
            v-for="doc in docsInKb(null)"
            :key="doc.id"
            class="kb-node-row kb-node-doc"
            :class="{ active: selectedDocId === doc.id }"
            type="button"
            @click="selectDoc(doc.id)"
          >
            <i class="kb-doc-dot">{{ extOf(doc.logical_name) }}</i>
            <span class="kb-node-name">{{ doc.logical_name }}</span>
          </button>
        </nav>
      </aside>

      <!-- 右侧：内容区 -->
      <section class="kb-main">
        <div class="kb-toolbar">
          <nav v-if="activeDoc" class="kb-crumbs">
            <template v-if="activeKb">{{ activeKb.name }}</template>
            <template v-else>当前项目</template>
          </nav>
          <div class="kb-toolbar-actions">
            <button class="kb-btn kb-btn-primary" type="button" @click="openUploadDialog">＋ 上传文档</button>
          </div>
        </div>

        <!-- 选中文档：查看器（全文 / 分段） -->
        <template v-if="activeDoc">
          <div class="kb-viewer">
            <header class="kb-viewer-header">
              <div class="kb-viewer-title">
                <strong :title="activeDoc.logical_name">{{ activeDoc.logical_name }}</strong>
                <small>{{ activeDoc.parser_version || '—' }} · {{ activeDoc.force_ocr ? 'OCR' : '文本' }} · {{ statusText(activeDoc.processing_status) }}</small>
              </div>
              <button class="kb-viewer-close" type="button" aria-label="关闭" @click="closeViewer">×</button>
            </header>
            <nav class="kb-viewer-tabs">
              <button type="button" :class="{ active: viewerTab === 'content' }" @click="viewerTab = 'content'">全文</button>
              <button type="button" :class="{ active: viewerTab === 'chunks' }" @click="viewerTab = 'chunks'">分段 ({{ docChunks.length }})</button>
            </nav>
            <div class="kb-viewer-body">
              <p v-if="viewerLoading" class="kb-viewer-state">加载中…</p>
              <p v-else-if="viewerError" class="kb-viewer-error">{{ viewerError }}</p>
              <article v-else-if="viewerTab === 'content'" class="kb-md" v-html="renderedContent"></article>
              <ol v-else class="kb-chunk-list">
                <li v-for="c in docChunks" :key="c.id" class="kb-chunk">
                  <div class="kb-chunk-meta">
                    <span class="kb-chunk-idx">#{{ c.chunk_index }}</span>
                    <span v-if="locatorText(c.locator)" class="kb-chunk-loc">{{ locatorText(c.locator) }}</span>
                  </div>
                  <p>{{ c.content }}</p>
                </li>
              </ol>
            </div>
          </div>
        </template>

        <!-- 选中知识库：文档卡片 -->
        <template v-else-if="selectedKbId && activeKb">
          <div class="kb-section-head"><h2>{{ activeKb.name }}</h2><span>{{ docsInKb(activeKb.id).length }} 篇文档</span></div>
          <div v-if="docsInKb(activeKb.id).length" class="kb-card-grid">
            <div v-for="doc in docsInKb(activeKb.id)" :key="doc.id" class="kb-card kb-card-doc" :class="{ selected: selectedDocId === doc.id }" role="button" tabindex="0" @click="selectDoc(doc.id)" @keyup.enter="selectDoc(doc.id)">
              <i class="kb-file-ico">{{ extOf(doc.logical_name) }}</i>
              <span class="kb-card-doc-name">{{ doc.logical_name }}</span>
              <span class="kb-card-doc-excerpt">{{ doc.media_type }}</span>
              <span class="kb-card-doc-meta">{{ doc.parser_version || '—' }} · {{ doc.force_ocr ? 'OCR' : '文本' }}</span>
              <span class="kb-card-doc-foot">
                <span :class="['kb-badge', doc.processing_status]">{{ statusText(doc.processing_status) }}</span>
                <button class="kb-del" type="button" @click.stop="deleteDoc(doc)">删除</button>
              </span>
            </div>
          </div>
          <div v-else class="kb-empty">暂无文档。</div>
        </template>

        <!-- 未选中知识库：全部挂载文档 -->
        <template v-else>
          <div class="kb-section-head"><h2>项目文档</h2></div>
          <div v-if="sources.length" class="kb-card-grid">
            <div v-for="doc in sources" :key="doc.id" class="kb-card kb-card-doc" :class="{ selected: selectedDocId === doc.id }" role="button" tabindex="0" @click="selectDoc(doc.id)" @keyup.enter="selectDoc(doc.id)">
              <i class="kb-file-ico">{{ extOf(doc.logical_name) }}</i>
              <span class="kb-card-doc-name">{{ doc.logical_name }}</span>
              <span class="kb-card-doc-excerpt">{{ doc.media_type }}</span>
              <span class="kb-card-doc-meta">{{ doc.parser_version || '—' }} · {{ doc.force_ocr ? 'OCR' : '文本' }}</span>
              <span class="kb-card-doc-foot">
                <span :class="['kb-badge', doc.processing_status]">{{ statusText(doc.processing_status) }}</span>
                <button class="kb-del" type="button" @click.stop="deleteDoc(doc)">删除</button>
              </span>
            </div>
          </div>
          <div v-else class="kb-empty">暂无文档。</div>
        </template>
      </section>
    </div>

    <!-- 上传弹窗 -->
    <div v-if="uploadModal" class="kb-modal-overlay" @click.self="uploadModal = null">
      <div class="kb-modal" role="dialog" aria-label="上传文档">
        <h3>上传文档</h3>
        <p class="kb-modal-file">{{ uploadModal.file.name }}</p>
        <p class="kb-modal-target">目标知识库：{{ activeKb?.name ?? '未分组' }}</p>
        <label class="kb-upload-option">
          <input v-model="uploadForceOcr" type="checkbox" />
          <span>OCR 识别（扫描件/图片 PDF 建议开启）</span>
        </label>
        <div class="kb-modal-actions">
          <button class="kb-btn" type="button" @click="uploadModal = null">取消</button>
          <button class="kb-btn kb-btn-primary" type="button" :disabled="uploading" @click="confirmUpload">{{ uploading ? '上传中…' : '上传' }}</button>
        </div>
      </div>
    </div>

    <!-- 创建知识库弹窗 -->
    <div v-if="createKbModal" class="kb-modal-overlay" @click.self="createKbModal = false">
      <div class="kb-modal" role="dialog" aria-label="创建知识库">
        <h3>创建知识库</h3>
        <input v-model="createKbName" placeholder="输入知识库名称" @keyup.enter="confirmCreateKb" />
        <div class="kb-modal-actions">
          <button class="kb-btn" type="button" @click="createKbModal = false">取消</button>
          <button class="kb-btn kb-btn-primary" type="button" :disabled="!createKbName.trim()" @click="confirmCreateKb">创建</button>
        </div>
      </div>
    </div>

    <!-- 挂载知识库弹窗 -->
    <div v-if="mountKbModal" class="kb-modal-overlay" @click.self="mountKbModal = false">
      <div class="kb-modal" role="dialog" aria-label="挂载知识库">
        <h3>挂载知识库</h3>
        <p class="kb-modal-note">选择要关联的知识库。</p>
        <p v-if="mountKbLoading" class="kb-modal-note">加载中…</p>
        <div v-else-if="!mountableKbs.length" class="kb-modal-note">没有可挂载的知识库。</div>
        <ul v-else class="kb-mount-list">
          <li v-for="kb in mountableKbs" :key="kb.id">
            <button type="button" @click="confirmMountKb(kb)">
              <span>{{ kb.name }}</span>
              <em>挂载</em>
            </button>
          </li>
        </ul>
        <div class="kb-modal-actions">
          <button class="kb-btn" type="button" @click="mountKbModal = false">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.kb-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.kb-sidebar {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  padding: 12px 10px 16px;
}
.kb-create {
  width: 100%;
  min-height: 38px;
  border: 1px dashed var(--brand);
  border-radius: 9px;
  background: var(--brand-soft);
  color: var(--brand);
  padding: 0 10px;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 750;
  cursor: pointer;
}
.kb-create:hover {
  background: color-mix(in srgb, var(--brand) 16%, transparent);
}
.kb-sidebar-actions {
  display: grid;
  gap: 6px;
}
.kb-mount {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--ink);
  padding: 0 10px;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 750;
  cursor: pointer;
}
.kb-mount:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.kb-modal-note {
  margin: 0;
  color: var(--muted);
  font-size: 0.76rem;
  line-height: 1.5;
}
.kb-mount-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 280px;
  overflow: auto;
}
.kb-mount-list li button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--ink);
  padding: 10px 12px;
  font: inherit;
  font-size: 0.82rem;
  font-weight: 700;
  cursor: pointer;
  text-align: left;
}
.kb-mount-list li button:hover {
  border-color: var(--brand);
}
.kb-mount-list li em {
  color: var(--brand);
  font-size: 0.74rem;
  font-style: normal;
  font-weight: 750;
}
.kb-tree-label {
  padding: 14px 6px 8px;
  color: var(--muted);
  font-size: 0.7rem;
  font-weight: 800;
}
.kb-tree {
  display: grid;
  gap: 2px;
}
.kb-node-children {
  display: grid;
  gap: 2px;
  margin-left: 16px;
  padding-left: 6px;
  border-left: 1px solid var(--line-soft);
}
.kb-node-row {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  min-height: 34px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--ink);
  padding: 0 8px;
  font: inherit;
  font-size: 0.78rem;
  text-align: left;
  cursor: pointer;
}
.kb-node-row:hover {
  background: var(--surface-muted);
}
.kb-node-row.active {
  background: var(--brand-soft);
  color: var(--brand);
  font-weight: 750;
}
.kb-caret {
  flex: 0 0 auto;
  font-size: 0.62rem;
  color: var(--muted);
  transition: transform 0.14s ease;
}
.kb-caret.collapsed {
  transform: rotate(-90deg);
}
.kb-folder-ico {
  display: grid;
  place-items: center;
  width: 20px;
  height: 16px;
  font-style: normal;
}
.kb-folder-ico.plain {
  background: rgb(118 110 104 / 0.22);
  color: var(--muted);
  font-size: 0.72rem;
}
.kb-node-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1 1 auto;
}
.kb-node-doc .kb-node-name {
  color: var(--muted);
}
.kb-node-doc.active .kb-node-name {
  color: var(--brand);
}
.kb-doc-dot {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 30px;
  height: 20px;
  border-radius: 4px;
  background: rgb(118 110 104 / 0.16);
  color: var(--muted);
  font-size: 0.52rem;
  font-style: normal;
  font-weight: 800;
}
.kb-del-mini {
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 0.85rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
}
.kb-node-row:hover .kb-del-mini {
  opacity: 1;
}
.kb-del-mini:hover {
  color: var(--danger);
}
.kb-main {
  min-width: 0;
  min-height: 440px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--surface);
}

/* 文档查看器 */
.kb-viewer {
  min-width: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  overflow: hidden;
}
.kb-viewer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line-soft);
}
.kb-viewer-title { min-width: 0; }
.kb-viewer-title strong {
  display: block;
  overflow: hidden;
  color: var(--ink);
  font-size: 0.92rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-viewer-title small { display: block; margin-top: 4px; color: var(--muted); font-size: 0.7rem; }
.kb-viewer-close {
  flex: none;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font-size: 1.1rem;
  line-height: 1;
  cursor: pointer;
}
.kb-viewer-close:hover { background: var(--surface-muted); color: var(--ink); }
.kb-viewer-tabs { display: flex; gap: 4px; padding: 10px 18px 0; border-bottom: 1px solid var(--line-soft); }
.kb-viewer-tabs button {
  border: 0;
  border-radius: 6px 6px 0 0;
  background: transparent;
  color: var(--muted);
  padding: 7px 12px;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 750;
  cursor: pointer;
}
.kb-viewer-tabs button.active { background: var(--brand-soft); color: var(--brand); }
.kb-viewer-body {
  padding: 18px 22px;
  max-height: calc(100vh - 320px);
  min-height: 160px;
  overflow: auto;
}
.kb-viewer-state,
.kb-viewer-error { margin: 0; color: var(--muted); font-size: 0.82rem; }
.kb-viewer-error { color: var(--danger); }

/* Markdown 全文（v-html 注入的内容不带 scoped 属性，需 :deep 命中内层） */
.kb-md :deep(p) { margin: 0 0 12px; color: var(--ink); font-size: 0.84rem; line-height: 1.75; }
.kb-md :deep(h1) { margin: 22px 0 12px; color: var(--ink); font-size: 1.28rem; letter-spacing: -0.02em; }
.kb-md :deep(h2) { margin: 20px 0 10px; color: var(--ink); font-size: 1.06rem; }
.kb-md :deep(h3) { margin: 18px 0 8px; color: var(--ink); font-size: 0.95rem; }
.kb-md :deep(h4) { margin: 16px 0 8px; color: var(--ink); font-size: 0.86rem; }
.kb-md :deep(ul),
.kb-md :deep(ol) { margin: 0 0 12px; padding-left: 22px; }
.kb-md :deep(li) { margin: 3px 0; color: var(--ink); font-size: 0.84rem; line-height: 1.7; }
.kb-md :deep(code) { border-radius: 4px; background: var(--surface-muted); color: var(--danger); padding: 1px 5px; font: 0.78rem ui-monospace, Consolas, monospace; }
.kb-md :deep(pre) { overflow: auto; margin: 0 0 12px; border-radius: 8px; background: var(--ink); color: var(--surface-muted); padding: 12px 14px; font: 0.76rem/1.6 Consolas, monospace; }
.kb-md :deep(pre code) { background: transparent; color: inherit; padding: 0; }
.kb-md :deep(blockquote) { margin: 0 0 12px; border-left: 3px solid var(--line); padding: 4px 14px; color: var(--muted); }
.kb-md :deep(table) { width: 100%; margin: 0 0 14px; border-collapse: collapse; font-size: 0.8rem; }
.kb-md :deep(th) { border-bottom: 2px solid var(--line); padding: 7px 10px; text-align: left; color: var(--ink); font-weight: 750; }
.kb-md :deep(td) { border-bottom: 1px solid var(--line-soft); padding: 7px 10px; }
.kb-md :deep(a) { color: var(--brand); }
.kb-md :deep(hr) { margin: 18px 0; border: 0; border-top: 1px solid var(--line-soft); }

/* 分段列表 */
.kb-chunk-list { display: grid; gap: 12px; margin: 0; padding: 0; list-style: none; }
.kb-chunk { border: 1px solid var(--line-soft); border-radius: 9px; background: var(--surface); padding: 12px 14px; }
.kb-chunk-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.kb-chunk-idx { border-radius: 5px; background: var(--brand-soft); color: var(--brand); padding: 1px 7px; font-size: 0.68rem; font-weight: 800; }
.kb-chunk-loc { color: var(--muted); font-size: 0.7rem; }
.kb-chunk p { margin: 0; color: var(--ink); font-size: 0.82rem; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.kb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  margin-bottom: 16px;
}
.kb-crumbs {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 0.78rem;
}
.kb-crumbs span:last-child {
  color: var(--ink);
  font-weight: 750;
}
.kb-crumb-sep {
  margin: 0 2px;
  color: var(--line);
  font-style: normal;
}
.kb-toolbar-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.kb-btn {
  min-height: 40px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--surface);
  color: var(--ink);
  padding: 0 14px;
  font: inherit;
  font-size: 14px;
  font-weight: 550;
  cursor: pointer;
}
.kb-btn:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.kb-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.kb-btn-primary {
  border-color: var(--brand);
  background: var(--brand);
  color: #fff;
}
.kb-btn-primary:hover {
  background: var(--brand);
  color: #fff;
}
.kb-section-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 2px 0 14px;
}
.kb-section-head h2 {
  margin: 0;
  color: var(--ink);
  font-size: 1.02rem;
  letter-spacing: -0.018em;
}
.kb-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}
.kb-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 172px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  color: var(--ink);
  padding: 16px;
  text-align: left;
  cursor: pointer;
  font: inherit;
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}
.kb-card:hover {
  box-shadow: 0 10px 24px rgb(43 39 35 / 0.1);
  transform: translateY(-2px);
}
.kb-card.selected {
  border-color: var(--brand);
}
.kb-file-ico {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 10px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 0.62rem;
  font-style: normal;
  font-weight: 800;
  letter-spacing: -0.01em;
}
.kb-card-doc-name {
  overflow: hidden;
  font-size: 0.82rem;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-card-doc-meta {
  color: var(--muted);
  font-size: 0.68rem;
}
.kb-card-doc-excerpt {
  overflow: hidden;
  color: var(--muted);
  font-size: 0.72rem;
  line-height: 1.55;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.kb-card-doc-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}
.kb-badge {
  align-self: flex-start;
  margin-top: auto;
  border-radius: 999px;
  background: var(--brand-soft);
  color: var(--brand);
  padding: 2px 10px;
  font-size: 0.66rem;
  font-weight: 800;
}
.kb-badge.READY {
  background: rgb(82 115 96 / 0.14);
  color: var(--success);
}
.kb-badge.FAILED {
  background: rgb(162 68 53 / 0.14);
  color: var(--danger);
}
.kb-badge.UPLOADED,
.kb-badge.PARSING,
.kb-badge.OCR_CHECKING,
.kb-badge.CHUNKING,
.kb-badge.INDEXING {
  background: rgb(152 102 26 / 0.14);
  color: var(--warning);
}
.kb-del {
  margin-left: auto;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: transparent;
  color: var(--muted);
  padding: 2px 10px;
  font: inherit;
  font-size: 0.68rem;
  cursor: pointer;
}
.kb-del:hover {
  border-color: var(--danger);
  color: var(--danger);
}
.kb-empty {
  color: var(--muted);
  font-size: 0.82rem;
  padding: 40px 0;
  text-align: center;
}
.kb-error {
  margin-bottom: 12px;
  border: 1px solid rgb(162 68 53 / 0.3);
  border-radius: 10px;
  background: rgb(162 68 53 / 0.08);
  color: var(--danger);
  padding: 10px 14px;
  font-size: 0.8rem;
}
.kb-retry {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink);
  padding: 4px 12px;
  font: inherit;
  font-size: 0.75rem;
  cursor: pointer;
}
.kb-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  background: rgb(43 39 35 / 0.35);
}
.kb-modal {
  display: grid;
  gap: 12px;
  width: 380px;
  border-radius: 14px;
  background: var(--surface);
  padding: 20px;
  box-shadow: 0 24px 60px rgb(43 39 35 / 0.25);
}
.kb-modal h3 {
  margin: 0;
  color: var(--ink);
  font-size: 1rem;
  letter-spacing: -0.015em;
}
.kb-modal input[type="text"],
.kb-modal > input {
  min-height: 38px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #fff;
  color: var(--ink);
  padding: 0 12px;
  font: inherit;
  font-size: 0.82rem;
  outline: none;
}
.kb-modal > input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 12%, transparent);
}
.kb-modal-file {
  margin: 0;
  color: var(--ink);
  font-size: 0.84rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-modal-target {
  margin: 0;
  color: var(--muted);
  font-size: 0.78rem;
}
.kb-upload-option {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 0.82rem;
  cursor: pointer;
}
.kb-upload-option input {
  width: 16px;
  height: 16px;
}
.kb-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
