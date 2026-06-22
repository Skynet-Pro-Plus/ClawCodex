import type { DiffPreview } from '../api/types'

type Props = {
  diffs: DiffPreview[]
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

export function DiffReviewPanel({ diffs, onApprove, onReject }: Props) {
  const pending = diffs.filter((diff) => diff.status === 'pending' || diff.status === 'approved')
  return (
    <section className="panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Diff approval</span>
          <h2>{pending.length ? `${pending.length} write${pending.length === 1 ? '' : 's'} need review` : 'No diffs pending approval'}</h2>
        </div>
        <span className={`status-pill ${pending.length ? 'warning' : 'success'}`}>{pending.length ? 'Needs approval' : 'Safe'}</span>
      </div>
      <div className="stack">
        {diffs.length === 0 ? (
          <p>File writes appear here before they touch disk.</p>
        ) : (
          diffs.map((diff) => (
            <article className="diff-card" key={diff.id}>
              <div className="diff-head">
                <strong>{diff.file_path}</strong>
                <span className="status-pill">{diff.status}</span>
              </div>
              <pre className="diff-block">{diff.unified_diff || 'No textual changes.'}</pre>
              <div className="actions">
                <button type="button" disabled={diff.status === 'applied'} onClick={() => onApprove(diff.id)}>Approve</button>
                <button type="button" className="danger-button" disabled={diff.status === 'rejected'} onClick={() => onReject(diff.id)}>Reject</button>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  )
}
