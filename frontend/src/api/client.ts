import type {
  ApiEnvelope,
  Attachment,
  DiffPreview,
  GitCheckpoint,
  PackInfo,
  ModelKeyStatus,
  OpenRouterModelsResponse,
  ModelRoles,
  ProjectProfile,
  RecentRepoRow,
  Task,
  TaskTimeline,
  TestRun,
} from './types'

const API_BASE = ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    throw new Error(typeof payload === 'string' ? payload : payload?.error?.message || response.statusText)
  }
  const envelope = payload as ApiEnvelope<T>
  if (envelope && typeof envelope === 'object' && 'ok' in envelope) {
    if (!envelope.ok) throw new Error(envelope.error?.message || 'Request failed')
    return envelope.data
  }
  return payload as T
}

export async function health(): Promise<{ ok: boolean; status: string; name: string }> {
  return request('/health')
}

export async function listTasks(limit = 100): Promise<Task[]> {
  return request(`/api/tasks?limit=${limit}`)
}

export async function listRecentRepos(limit = 50): Promise<RecentRepoRow[]> {
  return request(`/api/repos/recent?limit=${limit}`)
}

export async function createTask(payload: {
  repo_path: string
  prompt: string
  max_debug_attempts?: number
  attachment_ids?: string[]
  model_config?: Record<string, unknown>
}): Promise<Task> {
  return request('/api/tasks', { method: 'POST', body: JSON.stringify(payload) })
}

export async function startTask(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/start`, { method: 'POST', body: JSON.stringify({}) })
}

export async function approvePlan(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/approve-plan`, { method: 'POST' })
}

export async function retryCode(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/retry-code`, { method: 'POST' })
}

export async function cancelTask(taskId: string): Promise<Task> {
  return request(`/api/tasks/${taskId}/cancel`, { method: 'POST' })
}

export async function deleteTask(taskId: string): Promise<{ task_id: string; deleted: boolean }> {
  return request(`/api/tasks/${taskId}`, { method: 'DELETE' })
}

export async function pauseTask(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/pause`, { method: 'POST' })
}

export async function resumeTask(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/resume`, { method: 'POST' })
}

export async function getTimeline(taskId: string): Promise<TaskTimeline> {
  return request(`/api/tasks/${taskId}/timeline`)
}

export async function selfCheck(taskId: string): Promise<Record<string, unknown>> {
  return request(`/api/tasks/${taskId}/self-check`, { method: 'POST' })
}

export async function getActiveRules(payload: {
  repo_path: string
  task_id?: string
  enabled_packs?: string[]
  task_rules?: string
  temporary_instruction?: string
}): Promise<Record<string, unknown>> {
  return request('/api/rules/active', { method: 'POST', body: JSON.stringify(payload) })
}

export async function listPacks(repoPath: string): Promise<PackInfo[]> {
  return request(`/api/rules/packs?repo_path=${encodeURIComponent(repoPath)}`)
}

export async function scanProject(repoPath: string): Promise<ProjectProfile> {
  return request('/api/projects/scan', { method: 'POST', body: JSON.stringify({ repo_path: repoPath }) })
}

export async function getProjectMemory(repoPath: string): Promise<Array<Record<string, unknown>>> {
  return request(`/api/projects/memory?repo_path=${encodeURIComponent(repoPath)}`)
}

export async function addProjectMemory(payload: {
  repo_path: string
  kind: 'style' | 'fix' | 'failure' | 'bug' | 'note'
  content: string
  evidence?: unknown[]
}): Promise<Record<string, unknown>> {
  return request('/api/projects/memory', { method: 'POST', body: JSON.stringify(payload) })
}

export async function getModelRoles(): Promise<ModelRoles> {
  return request('/api/models/roles')
}

export async function updateModelRoles(payload: ModelRoles): Promise<ModelRoles> {
  return request('/api/models/roles', { method: 'PUT', body: JSON.stringify(payload) })
}

export async function getOpenRouterModels(): Promise<OpenRouterModelsResponse> {
  return request('/api/models/openrouter')
}

export async function getModelKeyStatus(): Promise<ModelKeyStatus> {
  return request('/api/settings/model-key/status')
}

export async function saveModelKey(apiKey: string): Promise<ModelKeyStatus> {
  return request('/api/settings/model-key', {
    method: 'POST',
    body: JSON.stringify({ provider: 'openrouter', api_key: apiKey }),
  })
}

export async function clearModelKey(): Promise<ModelKeyStatus> {
  return request('/api/settings/model-key', { method: 'DELETE' })
}

export async function approveDiff(previewId: string): Promise<DiffPreview> {
  return request(`/api/safety/diff-preview/${previewId}/approve`, { method: 'POST' })
}

export async function rejectDiff(previewId: string): Promise<DiffPreview> {
  return request(`/api/safety/diff-preview/${previewId}/reject`, { method: 'POST' })
}

export async function updateDiffContent(previewId: string, content: string): Promise<DiffPreview> {
  return request(`/api/safety/diff-preview/${previewId}/content`, { method: 'POST', body: JSON.stringify({ content }) })
}

export async function approveHunk(previewId: string, hunkId: string): Promise<Record<string, unknown>> {
  return request(`/api/safety/diff-preview/${previewId}/hunks/${hunkId}/approve`, { method: 'POST' })
}

export async function rejectHunk(previewId: string, hunkId: string): Promise<Record<string, unknown>> {
  return request(`/api/safety/diff-preview/${previewId}/hunks/${hunkId}/reject`, { method: 'POST' })
}

export async function approveAllDiffs(taskId: string): Promise<{ diffs: DiffPreview[]; verification?: Record<string, unknown> }> {
  return request(`/api/tasks/${taskId}/diffs/approve-all`, { method: 'POST' })
}

export async function rejectAllDiffs(taskId: string): Promise<{ diffs: DiffPreview[] }> {
  return request(`/api/tasks/${taskId}/diffs/reject-all`, { method: 'POST' })
}

export async function rollback(taskId: string, checkpointId: string, mode: 'clean' | 'restore_dirty'): Promise<Record<string, unknown>> {
  return request('/api/safety/rollback', {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId, checkpoint_id: checkpointId, mode }),
  })
}

export async function runTests(repoPath: string, taskId: string, command?: string): Promise<TestRun> {
  return request('/api/tools/run_tests', {
    method: 'POST',
    body: JSON.stringify({ repo_path: repoPath, task_id: taskId, command: command || null }),
  })
}

export async function uploadAttachment(file: File, taskId?: string): Promise<Attachment> {
  const form = new FormData()
  form.append('file', file)
  if (taskId) form.append('task_id', taskId)
  return request('/api/attachments', { method: 'POST', body: form })
}

export async function linkAttachment(taskId: string, attachmentId: string): Promise<Attachment> {
  return request(`/api/tasks/${taskId}/attachments/${attachmentId}`, { method: 'POST' })
}

export function attachmentContentUrl(attachmentId: string): string {
  return `/api/attachments/${attachmentId}/content`
}

export async function listAttachments(taskId: string): Promise<Attachment[]> {
  return request(`/api/tasks/${taskId}/attachments`)
}

export type {
  Attachment,
  DiffPreview,
  GitCheckpoint,
  ModelKeyStatus,
  ModelRoles,
  OpenRouterModelsResponse,
  PackInfo,
  ProjectProfile,
  RecentRepoRow,
  Task,
  TaskTimeline,
  TestRun,
}
