import { AttachmentDropzone } from './AttachmentDropzone'
import type { Attachment } from '../api/types'

type Props = {
  repoPath: string
  prompt: string
  intent: string
  deniedPaths: string
  attachments: Attachment[]
  enabledPhases: string[]
  running: boolean
  onRepoPathChange: (value: string) => void
  onPromptChange: (value: string) => void
  onIntentChange: (value: string) => void
  onDeniedPathsChange: (value: string) => void
  onAttachmentsChange: (attachments: Attachment[]) => void
  onEnabledPhasesChange: (phases: string[]) => void
  onRun: () => void
  onScan: () => void
}

const phaseOptions = [
  { id: 'PLAN', label: 'Plan' },
  { id: 'CODE', label: 'Code' },
  { id: 'TEST', label: 'Test' },
  { id: 'DEBUG', label: 'Debug' },
  { id: 'REVIEW', label: 'Review' },
]

export function SimpleTaskComposer({
  repoPath,
  prompt,
  intent,
  deniedPaths,
  attachments,
  enabledPhases,
  running,
  onRepoPathChange,
  onPromptChange,
  onIntentChange,
  onDeniedPathsChange,
  onAttachmentsChange,
  onEnabledPhasesChange,
  onRun,
  onScan,
}: Props) {
  return (
    <section className="panel composer-panel simple-composer">
      <div className="panel-heading">
        <span className="eyebrow">Start here</span>
        <h2>Describe what you want changed. ClawCodex will create a checkpoint, propose diffs, and wait for approval.</h2>
      </div>
      <label>
        Repository path
        <div className="inline-control">
          <input value={repoPath} onChange={(event) => onRepoPathChange(event.target.value)} />
          <button type="button" className="ghost-button" onClick={onScan}>Scan</button>
        </div>
      </label>
      <label>
        Request
        <textarea
          value={prompt}
          placeholder="Build a Windows Python GUI that says hello world."
          onChange={(event) => onPromptChange(event.target.value)}
        />
      </label>
      <AttachmentDropzone attachments={attachments} onAttachmentsChange={onAttachmentsChange} onIntentChange={onIntentChange} />
      {intent && (
        <label>
          Image intent
          <input value={intent} onChange={(event) => onIntentChange(event.target.value)} />
        </label>
      )}
      <section className="visible-phase-panel">
        <div>
          <span className="eyebrow">Mission phases</span>
          <p>Disabled phases are skipped after code approval.</p>
        </div>
        <div className="phase-grid">
          {phaseOptions.map((phase) => (
            <label key={phase.id} className="phase-toggle">
              <input
                type="checkbox"
                checked={enabledPhases.includes(phase.id)}
                disabled={phase.id === 'PLAN' || phase.id === 'CODE'}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...enabledPhases, phase.id]
                    : enabledPhases.filter((item) => item !== phase.id)
                  onEnabledPhasesChange(Array.from(new Set(['PLAN', 'CODE', ...next])))
                }}
              />
              {phase.label}
            </label>
          ))}
        </div>
      </section>
      <details className="compact-options">
        <summary>Safety options</summary>
        <label>
          Never touch these files
          <input value={deniedPaths} onChange={(event) => onDeniedPathsChange(event.target.value)} />
        </label>
      </details>
      <button className="primary-action" type="button" onClick={onRun} disabled={running || !prompt.trim()}>
        {running ? 'Running task...' : 'Run task'}
      </button>
    </section>
  )
}
