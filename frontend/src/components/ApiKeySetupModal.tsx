import { useState } from 'react'
import type { ModelKeyStatus } from '../api/types'

type Props = {
  open: boolean
  status: ModelKeyStatus | null
  message?: string
  saving: boolean
  onSave: (apiKey: string) => Promise<void>
  onSkip: () => void
}

export function ApiKeySetupModal({ open, status, message, saving, onSave, onSkip }: Props) {
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [error, setError] = useState('')
  const [changingSavedKey, setChangingSavedKey] = useState(false)

  const hasSavedKey = status?.configured && status.source === 'local_config' && !message
  const hasEnvKey = status?.configured && status.source === 'env' && !message
  const showChangePrompt = Boolean(hasSavedKey && !changingSavedKey)

  if (!open) return null

  async function submit() {
    setError('')
    if (!apiKey.trim()) {
      setError('Enter an OpenRouter API key to continue.')
      return
    }
    try {
      await onSave(apiKey)
      setApiKey('')
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : 'Unable to save API key.')
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="api-key-modal" role="dialog" aria-modal="true" aria-labelledby="api-key-title">
        <span className="eyebrow">{status?.configured ? 'Model settings' : 'First run setup'}</span>
        <h2 id="api-key-title">{showChangePrompt ? 'API key saved' : 'Connect OpenRouter'}</h2>
        <p>
          {showChangePrompt
            ? 'An OpenRouter API key is already saved locally. Would you like to change it?'
            : 'ClawCodex can run local templates now, but general coding missions need an OpenRouter API key saved on this machine.'}
          {' '}The key is stored by the backend and never sent back to the browser.
        </p>
        {hasEnvKey && <div className="modal-warning">A key is configured from the environment. Local changes will only apply when no OpenRouter environment key is set.</div>}
        {message && <div className="modal-warning">{message}</div>}
        {status && <small>Current status: {status.configured ? `configured from ${status.source}` : 'not configured'}</small>}
        {showChangePrompt ? (
          <div className="modal-actions">
            <button type="button" className="primary-action" onClick={() => setChangingSavedKey(true)}>
              Change saved key
            </button>
            <button type="button" className="ghost-button" onClick={onSkip}>
              Keep current key
            </button>
          </div>
        ) : (
          <>
            <label>
              OpenRouter API key
              <div className="inline-control">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  placeholder="sk-or-..."
                  onChange={(event) => setApiKey(event.target.value)}
                />
                <button type="button" className="ghost-button" onClick={() => setShowKey((value) => !value)}>
                  {showKey ? 'Hide' : 'Show'}
                </button>
              </div>
            </label>
            {error && <div className="modal-error">{error}</div>}
            <div className="modal-actions">
              <button type="button" className="primary-action" onClick={submit} disabled={saving}>
                {saving ? 'Validating...' : 'Validate and save locally'}
              </button>
              <button type="button" className="ghost-button" onClick={onSkip} disabled={saving}>
                Use local templates only for now
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
