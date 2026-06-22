import { EventTimeline } from './EventTimeline'
import type { MissionView } from '../lib/missionView'

type Props = {
  view: MissionView
}

export function MissionProgress({ view }: Props) {
  return (
    <section className="mission-card progress-card">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Mission progress</span>
          <h2>{view.title}</h2>
        </div>
        <span className="status-pill active">{view.currentStage}</span>
      </div>
      <div className="mission-stepper">
        {view.stages.map((step) => (
          <div key={step.stage} className={`mission-step ${step.state}`}>
            <span>{step.state === 'done' ? '✓' : step.state === 'active' ? '•' : ''}</span>
            <strong>{step.stage}</strong>
          </div>
        ))}
      </div>
      {view.llmWaitHint ? <p className="llm-wait-hint">{view.llmWaitHint}</p> : null}
      <EventTimeline events={view.events} />
    </section>
  )
}
