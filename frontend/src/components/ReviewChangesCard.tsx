import { useState } from 'react'
import type { DiffHunk, DiffPreview } from '../api/types'

type Props = {
  diffs: DiffPreview[]
  hunks?: DiffHunk[]
  running: boolean
  onApproveAll: () => void
  onRejectAll: () => void
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onApproveHunk?: (previewId: string, hunkId: string) => void
  onRejectHunk?: (previewId: string, hunkId: string) => void
  onUpdateContent?: (previewId: string, content: string) => void
}

export function ReviewChangesCard({ diffs, hunks = [], running, onApproveAll, onRejectAll, onApprove, onReject, onApproveHunk, onRejectHunk, onUpdateContent }: Props) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const pending = diffs.filter((diff) => diff.status === 'pending')
  if (!diffs.length) return null
  return (
    <section className="panel review-card">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Review changes</span>
          <h2>{pending.length ? `${pending.length} proposed write${pending.length === 1 ? '' : 's'}` : 'No pending writes'}</h2>
        </div>
        <div className="actions inline-actions">
          <button type="button" onClick={onApproveAll} disabled={!pending.length || running}>
            Approve changes and run tests
          </button>
          <button type="button" className="danger-button" onClick={onRejectAll} disabled={!pending.length || running}>
            Reject all
          </button>
        </div>
      </div>
      <div className="stack">
        {diffs.map((diff) => (
          <details key={diff.id} className="diff-card" open={diff.status === 'pending'}>
            <summary>
              <strong>{diff.file_path}</strong>
              <span className={`status-pill ${riskTone(diff.risk_level)}`}>{diff.risk_level || 'Low'} risk</span>
              <span className="status-pill">{diff.status}</span>
            </summary>
            <p className="receipt-risk">{diff.patch_summary || 'Patch summary unavailable.'} {diff.approval_reason || ''}</p>
            <pre className="diff-block">{diff.unified_diff || 'No textual changes.'}</pre>
            <label className="embedded-editor">
              Patch editor
              <textarea
                value={drafts[diff.id] ?? diff.proposed_content ?? ''}
                onChange={(event) => setDrafts((current) => ({ ...current, [diff.id]: event.target.value }))}
                placeholder="Edit proposed file content before approval."
              />
            </label>
            <button type="button" className="ghost-button" onClick={() => onUpdateContent?.(diff.id, drafts[diff.id] ?? diff.proposed_content ?? '')} disabled={running || !onUpdateContent}>
              Save patch draft
            </button>
            <div className="hunk-stack">
              {hunks.filter((hunk) => hunk.preview_id === diff.id).map((hunk) => (
                <div key={hunk.id} className="hunk-card">
                  <div className="diff-head">
                    <strong>{hunk.header}</strong>
                    <span className="status-pill">{hunk.status}</span>
                  </div>
                  <pre className="diff-block">{hunk.body || 'No hunk body.'}</pre>
                  <div className="actions">
                    <button type="button" onClick={() => onApproveHunk?.(diff.id, hunk.id)} disabled={hunk.status !== 'pending' || running}>Approve hunk</button>
                    <button type="button" className="danger-button" onClick={() => onRejectHunk?.(diff.id, hunk.id)} disabled={hunk.status !== 'pending' || running}>Reject hunk</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="actions">
              <button type="button" onClick={() => onApprove(diff.id)} disabled={diff.status !== 'pending' || running}>Approve file</button>
              <button type="button" className="danger-button" onClick={() => onReject(diff.id)} disabled={diff.status !== 'pending' || running}>Reject file</button>
            </div>
          </details>
        ))}
      </div>
    </section>
  )
}

function riskTone(risk?: string): string {
  if (risk === 'High') return 'danger'
  if (risk === 'Medium') return 'warning'
  return 'success'
}
