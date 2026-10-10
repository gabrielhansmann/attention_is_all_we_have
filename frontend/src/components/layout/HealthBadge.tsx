import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Health } from '@/types/api'

type State = { kind: 'loading' } | { kind: 'offline' } | { kind: 'ok'; health: Health }

export function HealthBadge() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    const ctrl = new AbortController()
    const check = () =>
      api
        .health(ctrl.signal)
        .then((health) => setState({ kind: 'ok', health }))
        .catch((e) => {
          if (!(e instanceof DOMException && e.name === 'AbortError')) setState({ kind: 'offline' })
        })
    check()
    const timer = setInterval(check, 30_000)
    return () => {
      ctrl.abort()
      clearInterval(timer)
    }
  }, [])

  let text = 'Checking backend'
  let tone = 'bg-muted-foreground/40'
  let bad = false
  if (state.kind === 'offline') { text = 'Backend offline'; tone = 'bg-destructive'; bad = true }
  else if (state.kind === 'ok') {
    const { health } = state
    if (health.status === 'ok') { text = 'Backend ready'; tone = 'bg-success' }
    else {
      const missing = [health.db !== 'ok' && 'database', !health.openai_key && 'OpenAI key'].filter(Boolean).join(' and ')
      text = `Backend degraded: ${missing}`; tone = 'bg-destructive'; bad = true
    }
  }
  return (
    <p className={cn('flex items-center gap-2 text-xs', bad ? 'font-medium text-destructive' : 'text-muted-foreground')}>
      <span className={cn('size-2 rounded-full', tone)} aria-hidden /> {text}
    </p>
  )
}
