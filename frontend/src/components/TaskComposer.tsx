import type { Attachment } from '../api/types'
import { AttachmentDropzone } from './AttachmentDropzone'

type Props = {
  repoPath: string
  prompt: string
  intent: string
  deniedPaths: string
  attachments: Attachment[]
  running: boolean
  onRepoPathChange: (value: string) => void
  onPromptChange: (value: string) => void
  onIntentChange: (value: string) => void
  onDeniedPathsChange: (value: string) => void
  onAttachmentsChange: (items: Attachment[]) => void
  onCreate: () => void
  onScan: () => void
}

export function TaskComposer({
  repoPath,
  prompt,
  intent,
  deniedPaths,
  attachments,
  running,
  onRepoPathChange,
  onPromptChange,
  onIntentChange,
  onDeniedPathsChange,
  onAttachmentsChange,
  onCreate,
  onScan,
}: Props) {
  return (
    <section className="panel composer-panel">
      <div className="panel-heading">
        <span className="eyebrow">Mission control</span>
        <h2>Tell ClawCodex what to build, fix, or understand.</h2>
      </div>
      <label>
        Repository path
        <div className="inline-control">
          <input value={repoPath} onChange={(event) => onRepoPathChange(event.target.value)} placeholder="d:\\clawcodex" />
          <button type="button" onClick={onScan}>Scan</button>
        </div>
      </label>
      <label>
        Task
        <textarea
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          placeholder="Describe the outcome. Include constraints, files, or what the screenshot should become."
        />
      </label>
      <label>
        Intent lock
        <input value={intent} onChange={(event) => onIntentChange(event.target.value)} placeholder="No new dependencies, preserve dark mode..." />
      </label>
      <label>
        Never touch these files
        <input value={deniedPaths} onChange={(event) => onDeniedPathsChange(event.target.value)} placeholder=".env, secrets.json, src/auth/**" />
      </label>
      <AttachmentDropzone attachments={attachments} onAttachmentsChange={onAttachmentsChange} onIntentChange={onIntentChange} />
      <button className="primary-action" type="button" disabled={!repoPath || !prompt || running} onClick={onCreate}>
        {running ? 'Orchestrating...' : 'Create task and start safely'}
      </button>
    </section>
  )
}
