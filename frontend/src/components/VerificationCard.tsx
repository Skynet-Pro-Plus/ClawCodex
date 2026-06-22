import type { TestRun } from '../api/types'

type Props = {
  tests: TestRun[]
  attempts: number
  maxAttempts: number
  onRunTests: () => void
}

export function VerificationCard({ tests, attempts, maxAttempts, onRunTests }: Props) {
  const latest = tests.at(-1)
  if (!latest) return null
  const firstError = latest.parsed_errors.at(0)
  return (
    <section className="panel verification-card">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Verification</span>
          <h2>Tests {latest.status}</h2>
        </div>
        <button type="button" onClick={onRunTests}>Run tests again</button>
      </div>
      <div className="metric-grid">
        <div><span>Command</span><strong>{latest.command}</strong></div>
        <div><span>Attempts</span><strong>{attempts} / {maxAttempts}</strong></div>
        <div><span>Exit</span><strong>{latest.exit_code ?? 'n/a'}</strong></div>
        <div><span>Duration</span><strong>{latest.duration_ms}ms</strong></div>
      </div>
      {firstError && (
        <article className="failure-card verification-error">
          <span>{String(firstError.type || 'failure')}</span>
          <strong>{String(firstError.message || 'No message')}</strong>
          <small>{String(firstError.file || '')}{firstError.line ? `:${String(firstError.line)}` : ''}</small>
        </article>
      )}
      <details className="raw-output">
        <summary>Show full output</summary>
        <pre className="diff-block">{[latest.stdout, latest.stderr].filter(Boolean).join('\n') || 'No output captured.'}</pre>
      </details>
    </section>
  )
}
