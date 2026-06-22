import type { ModelKeyStatus, PackInfo, RecentRepoRow, Task } from '../api/types'

function summarizePrompt(prompt: string): string {
  const first = prompt.split('\n')[0].trim()
  return first.length > 72 ? `${first.slice(0, 69)}…` : first || '(empty)'
}

export function MissionsPage({
  tasks,
  loading,
  error,
  onOpenMission,
  onCancelMission,
  onDeleteMission,
}: {
  tasks: Task[]
  loading: boolean
  error: string | null
  onOpenMission: (taskId: string) => void
  onCancelMission: (taskId: string) => void
  onDeleteMission: (taskId: string) => void
}) {
  if (loading) return <p className="nav-page-hint">Loading missions…</p>
  if (error) return <p className="nav-page-error">{error}</p>
  if (!tasks.length) return <p className="nav-page-hint">No missions yet. Start one from Mission Control.</p>
  return (
    <div className="nav-page-table-wrap">
      <table className="nav-page-table">
        <thead>
          <tr>
            <th>Mission</th>
            <th>Stage</th>
            <th>Repo</th>
            <th>Updated</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} className="mission-row" onClick={() => onOpenMission(t.id)}>
              <td title={t.prompt}>{summarizePrompt(t.prompt)}</td>
              <td>{t.stage}</td>
              <td className="nav-page-mono" title={t.repo_path}>
                {t.repo_path}
              </td>
              <td>{new Date(t.updated_at).toLocaleString()}</td>
              <td>
                <div className="mission-row-actions">
                  <button type="button" className="ghost-button" onClick={(ev) => { ev.stopPropagation(); onOpenMission(t.id) }}>
                    Open
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={t.stage === 'COMPLETE' || t.stage === 'FAILED'}
                    onClick={(ev) => { ev.stopPropagation(); onCancelMission(t.id) }}
                  >
                    Stop
                  </button>
                  <button type="button" className="ghost-button danger-button" onClick={(ev) => { ev.stopPropagation(); onDeleteMission(t.id) }}>
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function RepositoriesPage({
  repos,
  loading,
  error,
  onUseRepo,
}: {
  repos: RecentRepoRow[]
  loading: boolean
  error: string | null
  onUseRepo?: (path: string) => void
}) {
  if (loading) return <p className="nav-page-hint">Loading repositories…</p>
  if (error) return <p className="nav-page-error">{error}</p>
  if (!repos.length) return <p className="nav-page-hint">No repositories recorded yet. Run a mission to populate this list.</p>
  return (
    <div className="nav-page-table-wrap">
      <table className="nav-page-table">
        <thead>
          <tr>
            <th>Path</th>
            <th>Last used</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {repos.map((row) => (
            <tr key={row.repo_path}>
              <td className="nav-page-mono" title={row.repo_path}>
                {row.repo_path}
              </td>
              <td>{new Date(row.last_used_at).toLocaleString()}</td>
              <td>
                {onUseRepo ? (
                  <button type="button" className="ghost-button" onClick={() => onUseRepo(row.repo_path)}>
                    Use in composer
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TemplatesPage({
  packs,
  repoPath,
  loading,
  error,
}: {
  packs: PackInfo[]
  repoPath: string
  loading: boolean
  error: string | null
}) {
  if (loading) return <p className="nav-page-hint">Loading packs…</p>
  if (error) return <p className="nav-page-error">{error}</p>
  return (
    <div className="nav-page-stack">
      <p className="nav-page-hint">
        Rule packs under <code className="nav-page-mono">clawcodex-packs/</code> in <span className="nav-page-mono">{repoPath}</span>. Enable packs for the next mission from the Rules panel on Mission
        Control.
      </p>
      {!packs.length ? (
        <p className="nav-page-hint">No packs found. Add a directory under clawcodex-packs to ship reusable rules.</p>
      ) : (
        <ul className="nav-page-cards">
          {packs.map((pack) => (
            <li key={pack.id} className="nav-page-card">
              <strong>{pack.name}</strong>
              <small className="nav-page-mono">{pack.id}</small>
              <p>{pack.description || pack.path || 'No description.'}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function IntegrationsPage({
  keyStatus,
  onOpenSettings,
}: {
  keyStatus: ModelKeyStatus | null
  onOpenSettings: () => void
}) {
  return (
    <div className="nav-page-stack">
      <section className="nav-page-card">
        <strong>OpenRouter</strong>
        <p>
          API key: {keyStatus?.configured ? `configured (${keyStatus.source})` : 'not configured — models run in template mode until you add a key.'}
        </p>
        <button type="button" onClick={onOpenSettings}>
          Model settings
        </button>
      </section>
      <section className="nav-page-card nav-page-muted">
        <strong>Webhooks</strong>
        <p>Not configured. Future releases can notify external systems when missions complete.</p>
      </section>
      <section className="nav-page-card nav-page-muted">
        <strong>MCP / external tools</strong>
        <p>Not configured. Connect MCP servers from your environment when supported.</p>
      </section>
    </div>
  )
}
