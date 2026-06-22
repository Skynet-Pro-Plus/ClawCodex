import type { ProjectProfile } from '../api/types'

type Props = {
  profile?: ProjectProfile | null
  memory: Array<Record<string, unknown>>
  onRemember: (content: string) => void
}

export function ProjectMemoryPanel({ profile, memory, onRemember }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <span className="eyebrow">Project awareness</span>
        <h2>{profile ? 'Repo profile loaded' : 'Scan the repo to build context'}</h2>
      </div>
      {profile ? (
        <div className="project-facts">
          <Fact label="Languages" value={profile.languages.join(', ') || 'unknown'} />
          <Fact label="Frameworks" value={profile.frameworks.join(', ') || 'none detected'} />
          <Fact label="Package manager" value={profile.package_manager || 'unknown'} />
          <Fact label="Entry points" value={profile.entry_points.join(', ') || 'none detected'} />
          <Fact label="Files indexed" value={String(profile.file_count ?? 0)} />
        </div>
      ) : (
        <p>Project scan detects language, framework, package manager, test commands, entry points, config files, dependencies, and repo map data.</p>
      )}
      <div className="memory-list">
        <div className="panel-heading horizontal compact">
          <strong>Persistent memory</strong>
          <button type="button" onClick={() => onRemember('Remember: preserve project style and avoid unrelated refactors.')}>Remember style</button>
        </div>
        {memory.length ? memory.map((item) => (
          <article key={String(item.id)} className="memory-card">
            <span>{String(item.kind)}</span>
            <p>{String(item.content)}</p>
          </article>
        )) : <p>No saved memory yet.</p>}
      </div>
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="fact"><span>{label}</span><strong>{value}</strong></div>
}
