import type { Stage, StageRun, Task } from '../api/types'

const stages: Stage[] = ['IDLE', 'PLAN', 'CODE', 'TEST', 'DEBUG', 'REVIEW', 'COMPLETE']

type Props = {
  task?: Task | null
  stageRuns: StageRun[]
}

export function StageTimeline({ task, stageRuns }: Props) {
  return (
    <section className="panel timeline-panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Live stage timeline</span>
          <h2>{task ? task.prompt : 'Create a task to begin'}</h2>
        </div>
        <span className={`status-pill ${task?.stage === 'FAILED' ? 'danger' : task?.stage === 'COMPLETE' ? 'success' : 'active'}`}>
          {task?.stage || 'IDLE'}
        </span>
      </div>
      <div className="stage-rail">
        {stages.map((stage) => {
          const run = stageRuns.findLast((item) => item.stage === stage)
          const active = task?.stage === stage
          const passed = run?.status === 'passed' || (task?.stage === 'COMPLETE' && stage !== 'COMPLETE')
          return (
            <article key={stage} className={`stage-card ${active ? 'active' : ''} ${passed ? 'passed' : ''}`}>
              <span>{stage}</span>
              <strong>{run?.status || (stage === 'IDLE' ? 'ready' : 'waiting')}</strong>
              <small>{run?.model || 'model pending'}</small>
            </article>
          )
        })}
      </div>
      <div className="stage-log">
        {stageRuns.length === 0 ? (
          <p>No stage runs yet. ClawCodex will show plan, code, test, debug, and review activity here.</p>
        ) : (
          stageRuns.map((run) => (
            <details key={run.id}>
              <summary>
                <span>{run.stage}</span>
                <strong>{run.status}</strong>
                <small>{run.model}</small>
              </summary>
              <pre>{JSON.stringify(run.output || run.input, null, 2)}</pre>
            </details>
          ))
        )}
      </div>
    </section>
  )
}
