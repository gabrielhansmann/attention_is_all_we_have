import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'
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

  if (state.kind === 'loading') return <Badge variant="outline">Checking backend</Badge>
  if (state.kind === 'offline') return <Badge variant="destructive">Backend offline</Badge>
  const { health } = state
  if (health.status === 'ok') return <Badge variant="secondary">Backend ready</Badge>
  const missing = [health.db !== 'ok' && 'database', !health.openai_key && 'OpenAI key'].filter(Boolean).join(' and ')
  return <Badge variant="destructive">{`Backend degraded: ${missing}`}</Badge>
}
