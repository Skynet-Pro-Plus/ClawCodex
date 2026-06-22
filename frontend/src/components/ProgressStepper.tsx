import type { Stage, StageRun, Task } from '../api/types'

const steps: Stage[] = ['PLAN', 'CODE', 'TEST', 'DEBUG', 'REVIEW', 'COMPLETE']

type Props = {
  task: Task | null
  stageRuns: StageRun[]
}

export function ProgressStepper({ task, stageRuns }: Props) {
  const seen = new Set(stageRuns.map((run) => run.stage))
  return (
    <section className="panel progress-panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Progress</span>
          <h2>{task ? `Current step: ${task.stage}` : 'Ready when you are'}</h2>
        </div>
        {task && <span className="status-pill active">{task.stage}</span>}
      </div>
      <div className="simple-stepper">
        {steps.map((step) => {
          const active = task?.stage === step
          const passed = seen.has(step) && !active
          return (
            <div key={step} className={`simple-step ${active ? 'active' : ''} ${passed ? 'passed' : ''}`}>
              <span>{step}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
