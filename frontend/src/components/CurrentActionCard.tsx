import type { TaskTimeline } from '../api/types'

type Props = {
  timeline: TaskTimeline | null
  backendOnline: boolean
  onRetryHealth: () => void
}

export function CurrentActionCard({ timeline, backendOnline, onRetryHealth }: Props) {
  const task = timeline?.task ?? null
  const latestCode = [...(timeline?.stage_runs || [])].reverse().find((run) => run.stage === 'CODE')
  const blockedReason = latestCode?.output?.blocked_reason
  const friendlyBlockedReason = typeof blockedReason === 'string' && blockedReason.includes('OpenRouter authentication failed')
    ? `${blockedReason} In PowerShell: $env:OPENROUTER_API_KEY="your-key"; then restart the server.`
    : blockedReason
  const pendingDiffs = timeline?.diff_previews.filter((diff) => diff.status === 'pending').length || 0
  const tests = timeline?.test_runs || []
  const latestTest = tests.at(-1)

  let title = 'Ready to run'
  let body = 'Describe what you want changed. The agent will checkpoint the repo, propose diffs, and wait.'
  if (!backendOnline) {
    title = 'Backend offline'
    body = 'Start the FastAPI server, then retry health.'
  } else if (blockedReason) {
    title = 'Action needed'
    body = String(friendlyBlockedReason)
  } else if (pendingDiffs) {
    title = 'Waiting for your approval...'
    body = `${pendingDiffs} proposed file ${pendingDiffs === 1 ? 'change is' : 'changes are'} ready to review.`
  } else if (task?.stage === 'PLAN') {
    title = 'Planning request...'
    body = 'ClawCodex is turning the request into an execution plan.'
  } else if (task?.stage === 'CODE') {
    title = 'Generating code changes...'
    body = 'The CODE stage is preparing diff previews without touching files.'
  } else if (task?.stage === 'TEST') {
    title = 'Running tests...'
    body = latestTest ? `${latestTest.command} finished with ${latestTest.status}.` : 'Verification is starting.'
  } else if (task?.stage === 'COMPLETE') {
    title = 'Done'
    body = 'The task reached review and completion.'
  }

  return (
    <section className="panel current-action">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Current action</span>
          <h2>{title}</h2>
        </div>
        {!backendOnline && <button type="button" onClick={onRetryHealth}>Retry health</button>}
      </div>
      <p>{body}</p>
    </section>
  )
}
