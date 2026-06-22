import type { ModelOption, ModelRoles, StageRun } from '../api/types'

type Props = {
  roles?: ModelRoles | null
  stageRuns: StageRun[]
  modelOptions?: ModelOption[]
  modelSource?: string
  compact?: boolean
  onRolesChange: (roles: ModelRoles) => void
}

const modelOptionsFallback = [
  { id: 'anthropic/claude-opus-4.1', name: 'anthropic/claude-opus-4.1', company: 'anthropic', pricing: {} },
  { id: 'anthropic/claude-sonnet-4', name: 'anthropic/claude-sonnet-4', company: 'anthropic', pricing: {} },
  { id: 'google/gemini-2.5-pro', name: 'google/gemini-2.5-pro', company: 'google', pricing: {} },
  { id: 'openai/gpt-4.1-mini', name: 'openai/gpt-4.1-mini', company: 'openai', pricing: {} },
  { id: 'openai/gpt-4o', name: 'openai/gpt-4o', company: 'openai', pricing: {} },
]

export function ModelCostPanel({ roles, stageRuns, modelOptions, modelSource, compact = false, onRolesChange }: Props) {
  const modelsUsed = Array.from(new Set(stageRuns.map((run) => run.model).filter(Boolean)))
  const options = (modelOptions?.length ? modelOptions : modelOptionsFallback)
    .slice()
    .sort((a, b) => `${a.company || companyFromId(a.id)} ${a.id}`.localeCompare(`${b.company || companyFromId(b.id)} ${b.id}`))
  const update = (key: keyof ModelRoles, value: string) => {
    if (!roles) return
    onRolesChange({ ...roles, [key]: key === 'budget_usd' ? (value ? Number(value) : null) : value })
  }
  return (
    <section className={`panel model-routing-panel ${compact ? 'compact-model-routing' : ''}`}>
      <div className="panel-heading">
        <span className="eyebrow">Model routing and cost</span>
        <h2>{roles ? `${roles.optimize_for} optimization` : 'Role routing pending'}</h2>
        {modelSource && <p>Model list source: {modelSource}</p>}
      </div>
      {roles ? (
        <>
          <div className="role-grid">
            <RoleSelect label="Planner" value={roles.planner} options={options} onChange={(value) => update('planner', value)} />
            <RoleSelect label="Coder" value={roles.coder} options={options} onChange={(value) => update('coder', value)} />
            <RoleSelect label="Tester" value={roles.tester} options={options} onChange={(value) => update('tester', value)} />
            <RoleSelect label="Debugger" value={roles.debugger} options={options} onChange={(value) => update('debugger', value)} />
            <RoleSelect label="Reviewer" value={roles.reviewer} options={options} onChange={(value) => update('reviewer', value)} />
          </div>
          <div className="cost-controls">
            <label>
              Budget cap
              <input value={roles.budget_usd ?? ''} onChange={(event) => update('budget_usd', event.target.value)} placeholder="No cap" />
            </label>
            <label>
              Optimize for
              <select value={roles.optimize_for} onChange={(event) => update('optimize_for', event.target.value)}>
                <option value="balanced">balanced</option>
                <option value="speed">speed</option>
                <option value="quality">quality</option>
                <option value="cost">cost</option>
              </select>
            </label>
          </div>
        </>
      ) : <p>OpenRouter role configuration will appear here.</p>}
      {!compact && (
        <div className="model-used">
          <strong>Used this task</strong>
          {modelsUsed.length ? modelsUsed.map((model) => <span key={model}>{model}</span>) : <p>No model calls yet.</p>}
        </div>
      )}
    </section>
  )
}

function RoleSelect({ label, value, options, onChange }: { label: string; value: string; options: ModelOption[]; onChange: (value: string) => void }) {
  const merged = options.some((model) => model.id === value)
    ? options
    : [{ id: value, name: value, company: companyFromId(value), pricing: {} }, ...options]
  return (
    <label className="role">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {merged.map((model) => <option key={model.id} value={model.id}>{modelLabel(model)}</option>)}
      </select>
    </label>
  )
}

function modelLabel(model: ModelOption): string {
  const company = model.company || companyFromId(model.id)
  const release = model.released_at || 'release unknown'
  const prompt = formatTokenCost(model.pricing?.prompt)
  const completion = formatTokenCost(model.pricing?.completion)
  return `${company} / ${model.name || model.id} | ${release} | in ${prompt} / out ${completion}`
}

function companyFromId(id: string): string {
  return id.split('/', 1)[0] || 'unknown'
}

function formatTokenCost(value: unknown): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'cost unknown'
  return `$${(numeric * 1_000_000).toFixed(numeric * 1_000_000 >= 0.01 ? 2 : 4)}/1M`
}
