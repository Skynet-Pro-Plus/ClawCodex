import type { TaskTimeline } from '../api/types'

type Props = {
  timeline: TaskTimeline | null
}

export function CompletionReceipt({ timeline }: Props) {
  if (!timeline?.task || (timeline.task.stage !== 'COMPLETE' && timeline.task.stage !== 'FAILED')) {
    return null
  }
  const files = Array.from(new Set(timeline.diff_previews.map((diff) => diff.file_path)))
  const models = Array.from(new Set(timeline.stage_runs.map((run) => run.model).filter(Boolean)))
  const latestCheckpoint = timeline.git_checkpoints[0]
  return (
    <section className="panel receipt-panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Task receipt</span>
          <h2>{timeline.task.stage === 'COMPLETE' ? 'Completed with evidence' : 'Stopped with recovery context'}</h2>
        </div>
        <span className={`status-pill ${timeline.task.stage === 'COMPLETE' ? 'success' : 'danger'}`}>{timeline.task.stage}</span>
      </div>
      <div className="receipt-grid">
        <ReceiptFact label="Changed files" value={files.length ? files.join(', ') : 'No writes applied'} />
        <ReceiptFact label="Tests run" value={String(timeline.test_runs.length)} />
        <ReceiptFact label="Models used" value={models.length ? models.join(', ') : 'No model stage recorded'} />
        <ReceiptFact label="Rollback checkpoint" value={latestCheckpoint?.checkpoint_ref || 'No checkpoint'} />
      </div>
      <p className="receipt-risk">Remaining risks: review pending diffs, verify tests in your real environment, and keep rollback checkpoint until satisfied.</p>
    </section>
  )
}

function ReceiptFact({ label, value }: { label: string; value: string }) {
  return <div className="fact"><span>{label}</span><strong>{value}</strong></div>
}
