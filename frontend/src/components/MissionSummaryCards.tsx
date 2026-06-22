import type { MissionView } from '../lib/missionView'

type Props = {
  view: MissionView
  onViewPlan: () => void
  onViewDiff: () => void
}

export function MissionSummaryCards({ view, onViewPlan, onViewDiff }: Props) {
  return (
    <section className="summary-grid">
      <article className="mission-card mini-card">
        <span className="eyebrow">Latest plan</span>
        {view.latestPlanSummary ? <p>{view.latestPlanSummary}</p> : null}
        {view.latestPlanItems.length ? (
          <ol>
            {view.latestPlanItems.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
          </ol>
        ) : (
          <p>Plan will appear after mission starts.</p>
        )}
        <button type="button" className="link-button" onClick={onViewPlan}>View full plan</button>
      </article>
      <article className="mission-card mini-card">
        <span className="eyebrow">Test results</span>
        <h2>{view.latestTestStatus}</h2>
        {view.failedTest ? <p className="danger-text">{view.failedTest}</p> : <p>{view.latestTestCommand || 'Tests will appear after approval.'}</p>}
      </article>
      <article className="mission-card mini-card">
        <span className="eyebrow">Diff summary</span>
        <h2>{view.filesTouched} files changed</h2>
        <p><strong className="good-text">+{view.changedLines.added}</strong> <strong className="danger-text">-{view.changedLines.removed}</strong></p>
        <button type="button" className="link-button" onClick={onViewDiff}>View diff</button>
      </article>
      <article className="mission-card mini-card">
        <span className="eyebrow">Review notes</span>
        <p>{view.pendingDiffs.length ? 'Review proposed changes before applying them.' : 'No pending review notes.'}</p>
      </article>
    </section>
  )
}
