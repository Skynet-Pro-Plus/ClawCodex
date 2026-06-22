import type { PackInfo } from '../api/types'

type Props = {
  activeRules: string[]
  packs: PackInfo[]
  enabledPackIds: string[]
  onTogglePack: (packId: string, enabled: boolean) => void
  onSelfCheck?: () => void
  selfCheckDisabled?: boolean
}

export function RulesMissionPanel({
  activeRules,
  packs,
  enabledPackIds,
  onTogglePack,
  onSelfCheck,
  selfCheckDisabled,
}: Props) {
  const enabled = new Set(enabledPackIds)
  return (
    <section className="rules-mission-panel detail-section">
      <div className="rules-mission-header">
        <strong>Rules for next mission</strong>
        {onSelfCheck ? (
          <button type="button" className="ghost-button" onClick={onSelfCheck} disabled={selfCheckDisabled}>
            Run self-check
          </button>
        ) : null}
      </div>
      <p className="rules-system-note">
        Built-in <strong>system safety rules</strong> always apply and cannot be disabled. Workspace files (e.g. CLAWRULES.md) and the packs you enable below are layered on top.
      </p>
      <div className="rules-active-block">
        <span className="rules-active-label">Active on this mission (timeline)</span>
        {activeRules.length ? (
          <ul className="rules-active-list">
            {activeRules.slice(0, 12).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : (
          <small className="nav-page-hint">No rule summary yet — start or resume a mission to populate rules.</small>
        )}
      </div>
      <div className="rules-packs-block">
        <span className="rules-active-label">Enable packs (saved into the next task&apos;s model config)</span>
        {!packs.length ? (
          <small className="nav-page-hint">No packs found under clawcodex-packs for this repo.</small>
        ) : (
          <ul className="rules-pack-toggles">
            {packs.map((pack) => (
              <li key={pack.id}>
                <label className="rules-pack-row">
                  <input
                    type="checkbox"
                    checked={enabled.has(pack.id)}
                    onChange={(ev) => onTogglePack(pack.id, ev.target.checked)}
                  />
                  <span>
                    <strong>{pack.name}</strong>
                    <small>{pack.description || pack.id}</small>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
