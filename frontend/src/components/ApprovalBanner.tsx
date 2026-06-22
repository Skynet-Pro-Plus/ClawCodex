import type { DiffPreview } from '../api/types'

type Props = {
  pendingDiffs: DiffPreview[]
  blockedReason: string | null
  planApprovalNeeded?: boolean
  planSummary?: string
  planItems?: string[]
  promptCorrectionNote?: string
  running: boolean
  onApprove: () => void
  onReject: () => void
  onApprovePlan?: () => void
  onCancelMission?: () => void
  onViewDiff: () => void
  onOpenSettings: () => void
}

export function ApprovalBanner({
  pendingDiffs,
  blockedReason,
  planApprovalNeeded,
  planSummary,
  planItems = [],
  promptCorrectionNote,
  running,
  onApprove,
  onReject,
  onApprovePlan,
  onCancelMission,
  onViewDiff,
  onOpenSettings,
}: Props) {
  if (blockedReason) {
    const authBlocker = /key|auth|401|403|openrouter/i.test(blockedReason)
    const jsonBlocker = /json/i.test(blockedReason)
    const title = authBlocker ? 'Model setup needed' : jsonBlocker ? 'Model response issue' : 'Mission blocked'
    return (
      <section className="mission-banner warning-banner">
        <div className="banner-icon">!</div>
        <div>
          <h2>{title}</h2>
          <p>{blockedReason}</p>
        </div>
        <div className="banner-actions">
          {authBlocker ? <button type="button" onClick={onOpenSettings}>Open Settings</button> : null}
          {!authBlocker ? <button type="button" className="ghost-button" onClick={onOpenSettings}>Model Settings</button> : null}
        </div>
      </section>
    )
  }

  if (planApprovalNeeded) {
    return (
      <section className="mission-banner approval-banner">
        <div className="banner-icon">!</div>
        <div>
          <h2>Plan approval needed</h2>
          <p>{planSummary || 'Review this plan. CODE will not run until you approve it.'}</p>
          {planItems.length ? (
            <ul className="plan-preview-list">
              {planItems.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
            </ul>
          ) : null}
          {promptCorrectionNote ? <small>{promptCorrectionNote}</small> : null}
        </div>
        <div className="banner-actions">
          <button type="button" onClick={onApprovePlan} disabled={running}>Approve Plan and Code</button>
          {onCancelMission ? <button type="button" className="danger-button" onClick={onCancelMission} disabled={running}>Cancel Mission</button> : null}
        </div>
      </section>
    )
  }

  if (!pendingDiffs.length) {
    return (
      <section className="mission-banner idle-banner">
        <div className="banner-icon">+</div>
        <div>
          <h2>Ready for mission</h2>
          <p>Describe a task and ClawCodex will checkpoint, propose diffs, and wait for approval.</p>
          {promptCorrectionNote ? <small>{promptCorrectionNote}</small> : null}
        </div>
      </section>
    )
  }

  return (
    <section className="mission-banner approval-banner">
      <div className="banner-icon">!</div>
      <div>
        <h2>Approval needed</h2>
        <p>ClawCodex wants to apply {pendingDiffs.length} proposed file {pendingDiffs.length === 1 ? 'change' : 'changes'}.</p>
        <strong>{pendingDiffs[0]?.file_path}</strong>
      </div>
      <div className="banner-context">
        <span>What's changing?</span>
        <p>Review the diff before files are written. Tests run automatically after approval.</p>
      </div>
      <div className="banner-actions">
        <button type="button" onClick={onApprove} disabled={running}>Approve</button>
        <button type="button" className="danger-button" onClick={onReject} disabled={running}>Reject</button>
        <button type="button" className="ghost-button" onClick={onViewDiff}>View Diff</button>
      </div>
    </section>
  )
}
