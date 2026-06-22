import type { ReactNode } from 'react'

type Props = {
  title: string
  children: ReactNode
}

export function AdvancedDrawer({ title, children }: Props) {
  return (
    <details className="advanced-drawer">
      <summary>
        <strong>{title}</strong>
        <span>Open</span>
      </summary>
      <div className="advanced-drawer-body">{children}</div>
    </details>
  )
}
