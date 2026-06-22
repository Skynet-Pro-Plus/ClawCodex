type Props = {
  messages: string[]
  backendOnline: boolean
}

export function CommandConsole({ messages, backendOnline }: Props) {
  return (
    <section className="console">
      <div>
        <span className={`beacon ${backendOnline ? 'online' : 'offline'}`} />
        <strong>{backendOnline ? 'Backend healthy' : 'Backend offline'}</strong>
      </div>
      <div className="console-lines">
        {messages.length ? messages.map((message, index) => <p key={`${message}-${index}`}>{message}</p>) : <p>Console ready. Risky actions will explain themselves here.</p>}
      </div>
    </section>
  )
}
