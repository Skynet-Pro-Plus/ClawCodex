import type { MissionView } from '../lib/missionView'

type Props = {
  view: MissionView
  repoPath: string
}

export function TaskDetailsPanel({ view, repoPath }: Props) {
  const rows = [
    ['Current task', view.title],
    ['Repository', repoPath || 'Not selected'],
    ['Branch', view.branch],
    ['Model', view.latestModel],
    ['Files touched', String(view.filesTouched)],
    ['Running cost', formatCost(view.runningCostUsd)],
    ['Tests last run', view.latestTestStatus],
    ['Risk level', view.riskLevel],
    ['Rules active', String(view.activeRules.length)],
    ['Search evidence', String(view.searchCount)],
    ['Problems', String(view.diagnosticsCount)],
  ]

  return (
    <aside className="mission-card details-panel">
      <span className="eyebrow">Details</span>
      {rows.map(([label, value]) => (
        <div className="detail-row" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
      {view.activeRules.length > 0 && (
        <div className="detail-section">
          <strong>Active rules</strong>
          {view.activeRules.slice(0, 4).map((rule) => <small key={rule}>{rule}</small>)}
        </div>
      )}
    </aside>
  )
}

function formatCost(value: number): string {
  if (!value) return '$0.00'
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}
