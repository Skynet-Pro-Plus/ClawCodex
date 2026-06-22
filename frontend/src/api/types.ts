export type Stage = 'IDLE' | 'PLAN' | 'CODE' | 'TEST' | 'DEBUG' | 'REVIEW' | 'COMPLETE' | 'FAILED'

export type Task = {
  id: string
  repo_path: string
  prompt: string
  stage: Stage
  max_debug_attempts: number
  debug_attempts: number
  model_config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export type StageRun = {
  id: string
  task_id: string
  stage: Stage
  model: string
  status: 'queued' | 'running' | 'passed' | 'failed' | 'blocked'
  input: Record<string, unknown>
  output: Record<string, unknown>
  started_at: string
  finished_at: string | null
}

export type GitCheckpoint = {
  id: string
  task_id: string
  repo_path: string
  head_sha: string
  checkpoint_ref: string
  dirty_patch_path: string | null
  created_at: string
}

export type DiffPreview = {
  id: string
  task_id: string
  repo_path: string
  file_path: string
  before_sha256: string | null
  after_sha256: string
  proposed_content?: string
  unified_diff: string
  status: 'pending' | 'approved' | 'rejected' | 'applied'
  risk_level?: 'Low' | 'Medium' | 'High'
  approval_reason?: string
  patch_summary?: string
}

export type DiffHunk = {
  id: string
  preview_id: string
  task_id: string
  file_path: string
  header: string
  body: string
  status: 'pending' | 'approved' | 'rejected'
  risk_level: 'Low' | 'Medium' | 'High'
}

export type TestRun = {
  id: string
  task_id: string
  command: string
  status: 'passed' | 'failed' | 'error' | 'timeout' | 'blocked' | 'skipped'
  exit_code: number | null
  stdout: string
  stderr: string
  parsed_errors: Array<Record<string, unknown>>
  duration_ms: number
  created_at: string
}

export type ToolCall = {
  id: string
  task_id: string
  tool_name: string
  status: string
  input: string
  output: string
  created_at: string
}

export type Attachment = {
  id: string
  task_id: string | null
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  preview_url: string
  analysis_status: 'pending' | 'ready' | 'failed'
  analysis?: Record<string, unknown>
  created_at?: string
}

export type ProjectProfile = {
  repo_path: string
  languages: string[]
  frameworks: string[]
  package_manager: string | null
  test_commands: Array<Record<string, unknown>>
  entry_points: string[]
  config_files: string[]
  repo_map_snapshot_id: string
  file_count?: number
  dependencies?: Array<Record<string, unknown>>
}

export type ModelRoles = {
  planner: string
  coder: string
  tester: string
  debugger: string
  reviewer: string
  budget_usd: number | null
  optimize_for: 'speed' | 'quality' | 'cost' | 'balanced'
}

export type ModelKeyStatus = {
  configured: boolean
  provider: 'openrouter'
  source: 'env' | 'local_config' | 'none'
}

export type ModelOption = {
  id: string
  name: string
  company?: string
  released_at?: string | null
  context_length?: number | null
  pricing?: Record<string, unknown>
}

export type OpenRouterModelsResponse = {
  source: 'openrouter' | 'fallback'
  models: ModelOption[]
}

export type RuleSource = {
  id: string
  scope: string
  path: string
  priority: number
  enabled: boolean
  summary: string
}

export type TaskRules = {
  summary: string[]
  sources: RuleSource[]
  merged_content?: string
}

export type SearchEvidence = {
  id: string
  query: string
  kind: string
  results: Array<Record<string, unknown>>
}

export type Diagnostic = {
  id?: string
  file: string
  line: number | null
  column: number | null
  severity: string
  source: string
  code: string
  message: string
}

export type WorktreeRecord = {
  workspace_path: string
  branch: string
  status: string
}

export type PackInfo = {
  id: string
  name: string
  path: string
  description: string
  files: Record<string, boolean>
}

export type RecentRepoRow = {
  repo_path: string
  last_used_at: string
  project_profile: ProjectProfile | Record<string, unknown> | null
}

export type TaskTimeline = {
  task: Task
  stage_runs: StageRun[]
  tool_calls: ToolCall[]
  git_checkpoints: GitCheckpoint[]
  diff_previews: DiffPreview[]
  diff_hunks?: DiffHunk[]
  test_runs: TestRun[]
  attachments?: Attachment[]
  rules?: TaskRules | null
  search_evidence?: SearchEvidence[]
  diagnostics?: Diagnostic[]
  worktree?: WorktreeRecord | null
}

export type ApiEnvelope<T> = {
  ok: boolean
  data: T
  error?: { code: string; message: string; details?: Record<string, unknown> }
}
