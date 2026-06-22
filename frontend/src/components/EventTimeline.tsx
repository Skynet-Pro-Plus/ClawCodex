import type { MissionEvent } from '../lib/missionView'

type Props = {
  events: MissionEvent[]
}

export function EventTimeline({ events }: Props) {
  return (
    <div className="event-timeline">
      <h3>Event timeline</h3>
      {events.map((event, index) => (
        <div key={`${event.label}-${index}`} className="event-row">
          <span className={`event-dot ${event.tone}`} />
          <strong>{event.label}</strong>
          <small>{event.time || ''}</small>
        </div>
      ))}
    </div>
  )
}
