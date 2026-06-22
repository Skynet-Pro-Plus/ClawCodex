import type { GitCheckpoint } from '../api/types'

type Props = {
  checkpoints: GitCheckpoint[]
  onRollback: (checkpointId: string, mode: 'clean' | 'restore_dirty') => void
}

export function RollbackPanel({ checkpoints, onRollback }: Props) {
  const latest = checkpoints[0]
  return (
    <section className="panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Rollback safety</span>
          <h2>{latest ? 'Checkpoint ready' : 'No checkpoint yet'}</h2>
        </div>
        <span className={`status-pill ${latest ? 'success' : 'warning'}`}>{latest ? 'Rollback available' : 'Waiting'}</span>
      </div>
      {latest ? (
        <div className="checkpoint-card">
          <span>{latest.created_at}</span>
          <strong>{latest.checkpoint_ref}</strong>
          <small>{latest.head_sha.slice(0, 12)}</small>
          <div className="actions">
            <button type="button" onClick={() => onRollback(latest.id, 'clean')}>Rollback clean</button>
            <button type="button" onClick={() => onRollback(latest.id, 'restore_dirty')}>Restore dirty state</button>
          </div>
        </div>
      ) : <p>Every CODE stage creates a checkpoint before edits.</p>}
    </section>
  )
}
