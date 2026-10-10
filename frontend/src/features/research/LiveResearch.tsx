import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { api, ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { ChatMessage, Conversation, ConversationDetail } from '@/types/api'
import { StepCard } from './StepCard'

const POLL_MS = 2500
const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === 'pm'
  const result = message.kind === 'final_result'
  const decision = message.kind === 'system_note' && message.payload.decision !== undefined
  const label = result ? 'Result' : mine ? 'You' : 'Orchestrator'
  return (
    <div className={cn('flex flex-col gap-1 border p-4', mine ? 'bg-muted' : 'bg-background', result ? 'border-primary' : 'border-border',
      decision && 'border-0 border-l-2 border-l-border py-1')}>
      {!decision && <span className="text-xs tracking-wide text-muted-foreground">{label}</span>}
      <p className={cn('whitespace-pre-line text-sm', decision && 'text-muted-foreground')}>{message.content}</p>
    </div>
  )
}

export function LiveResearch() {
  const [list, setList] = useState<Conversation[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refreshList = useCallback((signal?: AbortSignal) =>
    api.conversations(signal).then((c) => { setList(c); setListError(null) })
      .catch((e) => !aborted(e) && setListError(errorText(e))), [])

  useEffect(() => {
    const ctrl = new AbortController()
    refreshList(ctrl.signal)
    return () => ctrl.abort()
  }, [refreshList])

  const convId = detail?.conversation.id
  const working = !!detail?.runs.some((r) => r.status === 'in_progress')

  // The orchestrator works in the background and can take minutes: read the thread again until the run ends.
  useEffect(() => {
    if (!convId || !working) return
    const timer = setInterval(() => {
      api.conversation(convId).then(setDetail).catch((e) => setError(errorText(e)))
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [convId, working])

  function open(id: string) {
    setDetailLoading(true)
    setError(null)
    api.conversation(id)
      .then(setDetail)
      .catch((e) => setError(errorText(e)))
      .finally(() => setDetailLoading(false))
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    const content = text.trim()
    if (content.length < 3 || sending || working) return
    setSending(true)
    setError(null)
    try {
      let id = detail?.conversation.id
      if (id) await api.postRequest(id, content)
      else id = (await api.createConversation(content)).conversation.id
      setDetail(await api.conversation(id))
      setText('')
      refreshList()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSending(false)
    }
  }

  const stepById = new Map((detail?.runs ?? []).flatMap((r) => r.steps).map((st) => [st.id, st]))
  const running = detail?.runs.flatMap((r) => r.steps).find((st) => st.status === 'running')

  return (
    <div className="flex flex-col gap-6" data-testid="live-research">
      <div>
        <h1 className="text-2xl">Research</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Ask a question. The orchestrator chooses which agents to call, reads each result, and decides whether it needs more.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <aside aria-labelledby="live-conv-h" className="flex flex-col gap-3 self-start">
          <div className="flex items-center justify-between gap-2">
            <h2 id="live-conv-h" className="text-lg">Conversations</h2>
            <Button variant="outline" size="sm" onClick={() => { setDetail(null); setError(null) }}>New</Button>
          </div>
          {listError && <p role="alert" className="text-sm text-destructive">{`Conversations unavailable: ${listError}`}</p>}
          {!listError && list.length === 0 && <p className="text-sm text-muted-foreground">No conversations yet.</p>}
          <ul className="flex flex-col">
            {list.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => open(c.id)}
                  aria-current={detail?.conversation.id === c.id ? 'true' : undefined}
                  className={cn('w-full border-l-2 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring',
                    detail?.conversation.id === c.id ? 'border-primary font-bold' : 'border-transparent')}>
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section aria-labelledby="live-thread-h" className="flex flex-col gap-4">
          <h2 id="live-thread-h" className="text-lg">{detail ? detail.conversation.title : 'Start a research request'}</h2>
          {detailLoading && <Skeleton className="h-32 w-full" aria-label="Loading conversation" />}
          {!detailLoading && detail?.messages.map((m) =>
            m.kind === 'step_card' && m.step_id
              ? <StepCard key={m.id} message={m} step={stepById.get(m.step_id)} />
              : <Bubble key={m.id} message={m} />)}
          {working && (
            <p role="status" className="text-sm text-muted-foreground">
              {running ? `${running.agent_name} is working. ` : 'The orchestrator is deciding. '}Results appear here as they arrive.
            </p>
          )}

          <form onSubmit={send} className="flex flex-col gap-3">
            <Label htmlFor="live-request">{detail ? 'Follow-up request' : 'Research request'}</Label>
            <Textarea id="live-request" rows={3} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="For example: What do US G60 owners dislike most about the infotainment?" />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div>
              <Button type="submit" size="lg" disabled={text.trim().length < 3 || sending || working}>
                {sending ? 'Sending' : working ? 'Working' : 'Send'}
              </Button>
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
