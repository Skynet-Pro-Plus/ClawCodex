import type { DiffPreview, Stage, TaskTimeline, TestRun } from '../api/types'

const stages: Stage[] = ['PLAN', 'CODE', 'TEST', 'DEBUG', 'REVIEW', 'COMPLETE']

export type MissionEvent = {
  label: string
  tone: 'success' | 'info' | 'warning' | 'danger'
  time?: string
}

export type MissionView = {
  title: string
  currentStage: Stage | 'IDLE'
  stages: Array<{ stage: Stage; state: 'done' | 'active' | 'idle' }>
  pendingDiffs: DiffPreview[]
  latestBlockedReason: string | null
  latestModel: string
  filesTouched: number
  changedLines: { added: number; removed: number }
  latestTestStatus: string
  latestTestCommand: string
  failedTest: string | null
  events: MissionEvent[]
  riskLevel: 'Low' | 'Medium' | 'High'
  checkpointReady: boolean
  rollbackAvailable: boolean
  runningCostUsd: number
  activeRules: string[]
  searchCount: number
  diagnosticsCount: number
  branch: string
  /** Shown while the latest CODE stage run is still `running` (OpenRouter in flight). */
  llmWaitHint: string | null
  latestPlanSummary: string
  latestPlanItems: string[]
  planApprovalNeeded: boolean
}

export function buildMissionView(timeline: TaskTimeline | null): MissionView {
  const task = timeline?.task
  const stageRuns = timeline?.stage_runs || []
  const diffs = timeline?.diff_previews || []
  const tests = timeline?.test_runs || []
  const checkpoints = timeline?.git_checkpoints || []
  const currentStage = task?.stage || 'IDLE'
  const completed = new Set(stageRuns.map((run) => run.stage))
  const latestPlan = [...stageRuns].reverse().find((run) => run.stage === 'PLAN')
  const latestPlanItems = planItems(latestPlan?.output)
  const latestPlanSummary = planSummary(latestPlan?.output)
  const latestCode = [...stageRuns].reverse().find((run) => run.stage === 'CODE')
  const codeRuns = stageRuns.filter((run) => run.stage === 'CODE')
  const latestCodeRun = codeRuns.at(-1)
  const llmWaitHint =
    latestCodeRun?.status === 'running'
      ? 'Calling the code model (typically up to 90 seconds)...'
      : null
  const latestRun = stageRuns.at(-1)
  const pendingDiffs = diffs.filter((diff) => diff.status === 'pending')
  const latestTest = tests.at(-1)
  const changedLines = diffStats(diffs)
  const filesTouched = new Set(diffs.map((diff) => diff.file_path)).size
  const failedTest = latestTest?.parsed_errors?.[0]?.message
    ? String(latestTest.parsed_errors[0].message)
    : latestTest?.status === 'failed'
      ? latestTest.command
      : null

  return {
    title: task ? summarizePrompt(task.prompt) : 'Start a new coding mission',
    currentStage,
    stages: stages.map((stage) => ({
      stage,
      state: currentStage === stage ? 'active' : completed.has(stage) ? 'done' : 'idle',
    })),
    pendingDiffs,
    latestBlockedReason: typeof latestCode?.output?.blocked_reason === 'string' ? latestCode.output.blocked_reason : null,
    latestModel: latestCode?.model || latestRun?.model || 'Not selected',
    filesTouched,
    changedLines,
    latestTestStatus: latestTest?.status || 'not run',
    latestTestCommand: latestTest?.command || '',
    failedTest,
    events: buildEvents(timeline),
    riskLevel: pendingDiffs.length > 3 || changedLines.removed > 100 ? 'High' : pendingDiffs.length ? 'Medium' : 'Low',
    checkpointReady: checkpoints.length > 0,
    rollbackAvailable: checkpoints.length > 0,
    runningCostUsd: sumRunCost(stageRuns),
    activeRules: timeline?.rules?.summary || [],
    searchCount: (timeline?.search_evidence || []).reduce((total, item) => total + item.results.length, 0),
    diagnosticsCount: (timeline?.diagnostics || []).length,
    branch: timeline?.worktree?.branch || 'current working tree',
    llmWaitHint,
    latestPlanSummary,
    latestPlanItems,
    planApprovalNeeded: currentStage === 'PLAN' && latestPlan?.status === 'passed',
  }
}

function summarizePrompt(prompt: string): string {
  const first = prompt.split('\n')[0].trim()
  return first.length > 80 ? `${first.slice(0, 77)}...` : first || 'Untitled mission'
}

function buildEvents(timeline: TaskTimeline | null): MissionEvent[] {
  if (!timeline) return [{ label: 'Waiting for mission input', tone: 'info' }]
  const events: MissionEvent[] = []
  for (const run of timeline.stage_runs) {
    events.push({
      label: `${run.stage} ${run.status}`,
      tone: run.status === 'passed' ? 'success' : run.status === 'blocked' ? 'warning' : run.status === 'failed' ? 'danger' : 'info',
      time: formatTime(run.finished_at || run.started_at),
    })
  }
  for (const diff of timeline.diff_previews) {
    events.push({ label: `${diff.status} ${basename(diff.file_path)}`, tone: diff.status === 'rejected' ? 'danger' : diff.status === 'pending' ? 'warning' : 'success' })
  }
  for (const test of timeline.test_runs) {
    events.push({
      label: testRunLabel(test),
      tone: testRunTone(test),
      time: formatTime(test.created_at),
    })
  }
  return events.slice(-8).reverse()
}

function diffStats(diffs: DiffPreview[]): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const diff of diffs) {
    for (const line of diff.unified_diff.split('\n')) {
      if (line.startsWith('+++') || line.startsWith('---')) continue
      if (line.startsWith('+')) added += 1
      if (line.startsWith('-')) removed += 1
    }
  }
  return { added, removed }
}

function basename(path: string): string {
  return path.split(/[\\/]/).at(-1) || path
}

function planSummary(output: Record<string, unknown> | undefined): string {
  if (!output) return ''
  if (typeof output.summary === 'string') return output.summary
  if (typeof output.plan === 'string') return output.plan === 'accepted' ? 'Plan accepted and ready for review.' : output.plan
  return 'Plan is ready for review.'
}

function planItems(output: Record<string, unknown> | undefined): string[] {
  if (!output) return []
  const explicitItems = Array.isArray(output.items) ? output.items.map(String).filter(Boolean) : []
  if (explicitItems.length) return explicitItems
  const items: string[] = []
  const rules = Array.isArray(output.rules_summary) ? output.rules_summary.map(String).filter(Boolean) : []
  if (rules.length) items.push(`Apply ${rules.length} active rule ${rules.length === 1 ? 'source' : 'sources'}.`)
  const searches = Array.isArray(output.search_evidence) ? output.search_evidence : []
  if (searches.length) items.push(`Use ${searches.length} search evidence ${searches.length === 1 ? 'pass' : 'passes'} for context.`)
  items.push('Create a checkpoint before proposing code changes.')
  items.push('Generate proposed diffs and wait for file approval.')
  items.push('Run enabled test/review phases after approval.')
  return items
}

function truncateDetail(text: string, maxLen: number): string {
  const t = text.trim()
  if (!t) return ''
  return t.length <= maxLen ? t : `${t.slice(0, maxLen - 1)}...`
}

function testRunLabel(test: TestRun): string {
  if (test.status === 'skipped') {
    const detail = truncateDetail(test.stderr || '', 96)
    return detail ? `Tests skipped (${detail})` : 'Tests skipped'
  }
  if (test.status === 'blocked') {
    const detail = truncateDetail(test.stderr || '', 96)
    return detail ? `Tests blocked (${detail})` : 'Tests blocked (policy)'
  }
  if (test.status === 'passed') return 'Tests passed'
  if (test.status === 'failed') return 'Tests failed'
  if (test.status === 'timeout') return 'Tests timed out'
  return `Tests ${test.status}`
}

function testRunTone(test: TestRun): MissionEvent['tone'] {
  if (test.status === 'passed') return 'success'
  if (test.status === 'failed') return 'danger'
  if (test.status === 'skipped') return 'info'
  if (test.status === 'blocked') return 'warning'
  return 'warning'
}

function formatTime(value?: string | null): string | undefined {
  if (!value) return undefined
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? undefined : date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function sumRunCost(stageRuns: TaskTimeline['stage_runs']): number {
  return stageRuns.reduce((total, run) => total + numericCost(run.output?.cost_usd), 0)
}

function numericCost(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}
