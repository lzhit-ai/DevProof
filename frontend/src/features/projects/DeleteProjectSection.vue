<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { deleteProject, selectedProject, selectedProjectId } from './project-context'

const router = useRouter()
const dialog = ref<HTMLDialogElement | null>(null)
const target = ref<{ id: string; name: string } | null>(null)
const confirmation = ref('')
const busy = ref(false)
const error = ref('')
const canConfirm = computed(() => !!target.value && confirmation.value === target.value.name && !busy.value)

function openDialog() {
  const project = selectedProject.value
  if (!project?.can_delete) return
  target.value = { id: project.id, name: project.name }
  confirmation.value = ''
  error.value = ''
  dialog.value?.showModal()
}

function closeDialog() {
  if (busy.value) return
  dialog.value?.close()
  target.value = null
  confirmation.value = ''
  error.value = ''
}

async function submit() {
  const project = target.value
  if (!project || !canConfirm.value) return
  busy.value = true
  error.value = ''
  try {
    await deleteProject(project.id, confirmation.value)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '项目删除失败，请稍后重试'
    busy.value = false
    return
  }
  busy.value = false
  closeDialog()
  await router.replace('/workbench')
}

watch(selectedProjectId, () => { if (!busy.value) closeDialog() })
</script>

<template>
  <section v-if="selectedProject" class="project-delete-section" aria-labelledby="project-delete-heading">
    <div>
      <h2 id="project-delete-heading">删除项目</h2>
      <p>删除后，所有成员都将无法进入该项目。历史审查与交付记录会在后台保留。</p>
      <small v-if="!selectedProject.can_delete">仅项目管理员可以删除项目。</small>
    </div>
    <button v-if="selectedProject.can_delete" class="delete-project-button" type="button" @click="openDialog">删除项目</button>
  </section>
  <dialog ref="dialog" class="project-delete-dialog" aria-labelledby="project-delete-title" aria-describedby="project-delete-description" @cancel.prevent="closeDialog">
    <form :aria-busy="busy" @submit.prevent="submit">
      <h2 id="project-delete-title">删除「{{ target?.name }}」？</h2>
      <p id="project-delete-description">项目将从工作台移除，所有成员将无法再访问。历史数据在后台保留，当前不提供恢复入口。GitHub 仓库与其他项目已挂载的知识库不受影响。</p>
      <label for="delete-project-confirmation">请输入项目名称 <strong>{{ target?.name }}</strong> 确认</label>
      <input id="delete-project-confirmation" v-model="confirmation" :disabled="busy" :aria-invalid="!!error" :aria-describedby="error ? 'delete-project-error' : undefined" autocomplete="off" :spellcheck="false" maxlength="200" placeholder="完整项目名称" required @input="error = ''" />
      <p v-if="error" id="delete-project-error" class="project-delete-error" role="alert">{{ error }}</p>
      <div class="project-delete-actions">
        <button type="button" :disabled="busy" autofocus @click="closeDialog">取消</button>
        <button class="delete-project-button delete-project-confirm" type="submit" :disabled="!canConfirm">{{ busy ? '正在删除…' : '确认删除项目' }}</button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.project-delete-section { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 32px; padding: 24px 0 8px; border-top: 1px solid var(--line); }
.project-delete-section h2 { margin: 0 0 8px; color: var(--ink); font-size: 15px; font-weight: 600; }
.project-delete-section p, .project-delete-section small { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.project-delete-section small { display: block; margin-top: 4px; }
.delete-project-button { flex-shrink: 0; min-height: 36px; padding: 8px 14px; border: 1px solid #dec4c6; border-radius: 7px; background: var(--surface); color: #a3343e; font: inherit; font-size: 13px; cursor: pointer; }
.delete-project-button:hover:not(:disabled) { background: #fff2f2; border-color: #bd6970; }
.project-delete-dialog { box-sizing: border-box; width: min(480px, calc(100vw - 32px)); max-height: calc(100dvh - 48px); margin: auto; padding: 28px; overflow-y: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); color: var(--ink); box-shadow: 0 20px 70px #142b4f26; }
.project-delete-dialog::backdrop { background: #16263d66; }
.project-delete-dialog h2 { margin: 0 0 12px; overflow-wrap: anywhere; font-size: 20px; line-height: 1.5; }
.project-delete-dialog p { margin: 0 0 22px; color: var(--muted); font-size: 13px; line-height: 1.9; }
.project-delete-dialog label { display: block; margin-bottom: 8px; overflow-wrap: anywhere; font-size: 13px; line-height: 1.8; }
.project-delete-dialog input { box-sizing: border-box; width: 100%; min-height: 42px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); color: var(--ink); font: inherit; font-size: 14px; }
.project-delete-dialog input:focus-visible, button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
.project-delete-dialog .project-delete-error { margin: 12px 0 0; color: #a3343e; }
.project-delete-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 24px; }
.project-delete-actions button { min-height: 38px; padding: 8px 14px; border: 1px solid var(--line); border-radius: 7px; background: var(--surface); color: var(--ink); font: inherit; font-size: 13px; cursor: pointer; }
.project-delete-actions .delete-project-confirm { border-color: #a3343e; background: #a3343e; color: white; }
.project-delete-actions .delete-project-confirm:hover:not(:disabled) { border-color: #862a33; background: #862a33; }
button:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 640px) { .project-delete-section { align-items: flex-start; flex-direction: column; gap: 14px; }.project-delete-dialog { padding: 22px; } }
</style>
