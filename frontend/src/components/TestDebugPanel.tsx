import type { TestRun } from '../api/types'

type Props = {
  tests: TestRun[]
  debugAttempts: number
  maxDebugAttempts: number
  onRunTests: () => void
  onStop: () => void
}

export function TestDebugPanel({ tests, debugAttempts, maxDebugAttempts, onRunTests, onStop }: Props) {
  const latest = tests.at(-1)
  return (
    <section className="panel">
      <div className="panel-heading horizontal">
        <div>
          <span className="eyebrow">Test and debug loop</span>
          <h2>{latest ? `Latest test ${latest.status}` : 'No tests have run yet'}</h2>
        </div>
        <div className="actions inline-actions">
          <button type="button" onClick={onRunTests}>Run tests again</button>
          <button type="button" className="danger-button" onClick={onStop}>Stop after this attempt</button>
        </div>
      </div>
      <div className="metric-grid">
        <div><span>Attempts</span><strong>{debugAttempts} / {maxDebugAttempts}</strong></div>
        <div><span>Duration</span><strong>{latest ? `${latest.duration_ms}ms` : 'none'}</strong></div>
        <div><span>Exit</span><strong>{latest?.exit_code ?? 'n/a'}</strong></div>
      </div>
      {latest ? (
        <div className="test-output">
          <strong>{latest.command}</strong>
          {latest.parsed_errors.length ? (
            latest.parsed_errors.map((error, index) => (
              <article className="failure-card" key={index}>
                <span>{String(error.type || 'failure')}</span>
                <strong>{String(error.message || 'No message')}</strong>
                <small>{String(error.file || '')}{error.line ? `:${String(error.line)}` : ''}</small>
              </article>
            ))
          ) : (
            <p>No parsed failures. Raw output is still stored in the timeline.</p>
          )}
        </div>
      ) : (
        <p>Approved writes will automatically feed test output back into DEBUG.</p>
      )}
    </section>
  )
}
