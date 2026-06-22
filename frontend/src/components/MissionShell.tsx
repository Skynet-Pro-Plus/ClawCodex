import type { ReactNode } from 'react'

export type ShellNavId = 'mission' | 'missions' | 'repos' | 'templates' | 'integrations'

type Props = {
  backendOnline: boolean
  keyConfigured: boolean
  activeNav: ShellNavId
  onNavigate: (id: ShellNavId) => void
  onNewMission: () => void
  onOpenSettings: () => void
  children: ReactNode
}

const NAV_ITEMS: Array<{ id: ShellNavId; label: string }> = [
  { id: 'mission', label: 'Mission Control' },
  { id: 'missions', label: 'Missions' },
  { id: 'repos', label: 'Repositories' },
  { id: 'templates', label: 'Templates' },
  { id: 'integrations', label: 'Integrations' },
]

export function MissionShell({
  backendOnline,
  keyConfigured,
  activeNav,
  onNavigate,
  onNewMission,
  onOpenSettings,
  children,
}: Props) {
  return (
    <main className="mission-shell">
      <aside className="mission-sidebar">
        <strong className="brand">ClawCodex</strong>
        <nav>
          {NAV_ITEMS.map(({ id, label }) => (
            <button key={id} type="button" className={activeNav === id ? 'nav-active' : ''} onClick={() => onNavigate(id)}>
              <span>{label}</span>
            </button>
          ))}
          <button type="button" onClick={onOpenSettings}>
            <span>Settings</span>
          </button>
        </nav>
        <div className="plan-card">
          <span>Local Agent</span>
          <strong>{keyConfigured ? 'Model ready' : 'Template mode'}</strong>
          <button type="button" className="ghost-button" onClick={onOpenSettings}>
            Model settings
          </button>
        </div>
      </aside>
      <section className="mission-main">
        <header className="mission-topbar">
          <div className="agent-status">
            <span className={`beacon ${backendOnline ? 'online' : ''}`} />
            {backendOnline ? 'Agent online' : 'Agent offline'}
          </div>
          <div className="top-actions">
            <button type="button" onClick={onNewMission}>
              New mission
            </button>
            <button type="button" className="ghost-button" onClick={onOpenSettings}>
              Settings
            </button>
            <span className="user-badge">SP</span>
          </div>
        </header>
        {children}
      </section>
    </main>
  )
}
