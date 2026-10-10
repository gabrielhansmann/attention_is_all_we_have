import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ArrowUp, CheckCircle2, Globe2, Route, Sparkles, Loader2 } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { ChatMessage, ConversationDetail } from '@/types/api'
import { useChats } from './chat-store'
import { Prose } from '@/features/sources/Prose'
import { findingIndex, type Finding } from '@/features/sources/citations'
import { SourceViewerProvider } from '@/features/sources/SourceViewer'
import { StepCard } from './StepCard'
import type { ModelScope } from '@/features/models/types'

const POLL_MS = 2500
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

const SUGGESTIONS = [
  'What do US G60 owners dislike most about the infotainment?',
  'How do EU and CN customers differ on driver assistance for the G70?',
  'Which equipment options for the F70 get the most feature requests?',
]

function Avatar() {
  return <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-primary/10 text-primary" aria-hidden><Sparkles className="size-4" /></span>
}

function Message({ message, findings }: { message: ChatMessage; findings: Map<string, Finding> }) {
  if (message.role === 'pm') {
    return (
      <div className="rise flex justify-end">
        <p className="max-w-[85%] whitespace-pre-line rounded-3xl rounded-br-lg bg-primary px-4 py-2.5 text-[0.95rem] leading-relaxed text-primary-foreground">{message.content}</p>
      </div>
    )
  }
  if (message.kind === 'system_note' && message.payload.decision !== undefined) {
    const decision = message.payload.decision as { agent?: string; reason?: string; position?: number }
    return (
      <div className="rise sm:ml-11 flex items-start gap-2 text-sm text-muted-foreground">
        <Route className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          <span className="font-medium text-foreground">{`${decision.position ? `Step ${decision.position}: ` : ''}${decision.agent ?? 'Agent'}`}</span>
          {decision.reason ? <span>{`. Why: ${decision.reason}`}</span> : <span>.</span>}
        </p>
      </div>
    )
  }
  if (message.kind === 'final_result') {
    const reqs = Number(message.payload.requirements) || 0
    const hasDossier = message.payload.dossier === true || message.content.startsWith('# Research dossier')
    const written = message.payload.written_by === 'orchestrator'
    return (
      <div className="rise flex gap-3">
        <Avatar />
        <div className="min-w-0 flex-1 rounded-2xl border border-primary/30 bg-accent/60 p-4 sm:p-5">
          <p className="mb-3 flex items-center gap-1.5 text-xs font-medium text-accent-foreground"><CheckCircle2 className="size-4" aria-hidden /> Research finished</p>
          <Prose text={message.content} findings={findings} collapse={written ? [] : hasDossier ? ['Accepted steps', 'Audit trail', 'Sources'] : ['*']} />
          {(reqs > 0 || hasDossier) && (
            <div className="mt-4 flex flex-wrap gap-2">
              {reqs > 0 && <a href="#requirements" className="inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm focus-visible:outline-2 focus-visible:outline-ring">{`Review ${reqs} requirement${reqs === 1 ? '' : 's'}`}</a>}
              {hasDossier && <a href="#dossiers" className="inline-flex h-10 items-center rounded-xl border border-border bg-background px-4 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">Open dossier</a>}
            </div>
          )}
        </div>
      </div>
    )
  }
  return (
    <div className="rise flex gap-3">
      <Avatar />
      <Prose text={message.content} findings={findings} className="min-w-0 flex-1 pt-1" />
    </div>
  )
}

export function LiveResearch({ modelScope }: { modelScope?: ModelScope } = {}) {
  const chats = useChats()
  const [modelActiveId, setModelActiveId] = useState<string | null>(modelScope?.conversation_id ?? null)
  const activeId = modelScope ? modelActiveId : chats.activeId
  const select = modelScope ? setModelActiveId : chats.select
  const refresh = chats.refresh
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)

  const convId = detail?.conversation.id
  const working = !!detail?.runs.some((r) => r.status === 'in_progress')

  // The sidebar picks the conversation; load it when it changes. A conversation just created here is already loaded.
  useEffect(() => {
    if (activeId === null) { setDetail(null); setError(null); return }
    if (activeId === convId) return
    const ctrl = new AbortController()
    setDetailLoading(true)
    setError(null)
    api.conversation(activeId, ctrl.signal)
      .then(setDetail)
      .catch((e) => { if (!(e instanceof DOMException && e.name === 'AbortError')) setError(errorText(e)) })
      .finally(() => setDetailLoading(false))
    return () => ctrl.abort()
  }, [activeId, convId])

  // The orchestrator works in the background and can take minutes: read the thread again until the run ends.
  useEffect(() => {
    if (!convId || !working) return
    const timer = setInterval(() => {
      api.conversation(convId).then(setDetail).catch((e) => setError(errorText(e)))
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [convId, working])

  const count = detail?.messages.length ?? 0
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [count, working, detailLoading])

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    const content = text.trim()
    if (content.length < 3 || sending || working) return
    setSending(true)
    setError(null)
    try {
      let id = detail?.conversation.id
      if (id) await api.postRequest(id, content)
      else id = (await api.createConversation(content, modelScope)).conversation.id
      const next = await api.conversation(id)
      setDetail(next)
      select(id)
      setText('')
      void refresh()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSending(false)
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit() }
  }

  const stepById = new Map((detail?.runs ?? []).flatMap((r) => r.steps).map((st) => [st.id, st]))
  const findings = findingIndex(detail?.messages ?? [])
  const running = detail?.runs.flatMap((r) => r.steps).find((st) => st.status === 'running')
  const empty = !detail && !detailLoading
  const label = detail ? 'Follow-up request' : 'Research request'
  const canSend = text.trim().length >= 3 && !sending && !working

  const composer = (
    <form onSubmit={submit} className="w-full">
      <div className="rounded-3xl border border-input bg-background p-2 shadow-md transition-colors focus-within:border-ring focus-within:ring-4 focus-within:ring-ring/15">
        <label htmlFor="live-request" className="sr-only">{label}</label>
        <textarea ref={input} id="live-request" rows={1} value={text} onChange={(e) => setText(e.target.value)} onKeyDown={onKey}
          placeholder={detail ? 'Ask a follow-up' : 'Ask about customer feedback, catalogs or markets'}
          className="field-sizing-content block max-h-48 min-h-11 w-full resize-none bg-transparent px-3 py-2.5 text-[0.95rem] outline-none placeholder:text-muted-foreground" />
        <div className="flex items-center justify-between gap-2 px-2 pb-1">
          <p className="text-xs text-muted-foreground">Enter to send, Shift+Enter for a new line</p>
          <button type="submit" disabled={!canSend} aria-label={sending ? 'Sending' : working ? 'Working' : 'Send'}
            className="grid size-9 place-items-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary-active focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:bg-muted disabled:text-muted-foreground">
            {sending || working ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </div>
      </div>
      {error && <p role="alert" className="mt-2 px-3 text-sm text-destructive">{error}</p>}
    </form>
  )

  return (
    <SourceViewerProvider>
    <div className="flex min-h-0 flex-1 flex-col" data-testid="live-research">
      <header className="flex min-h-14 shrink-0 items-center border-b border-border px-6">
        {modelScope ? <h2 className="text-sm font-semibold">Model chat</h2> : <h1 className="truncate text-sm font-semibold">{detail ? detail.conversation.title : 'New chat'}</h1>}
      </header>

      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto px-4 py-10">
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary"><Sparkles className="size-7" /></span>
            <h2 className={modelScope ? 'text-xl' : 'text-2xl sm:text-3xl'}>{modelScope ? `Ask about ${modelScope.name}` : 'What would you like to research?'}</h2>
            <p className="max-w-lg text-sm text-muted-foreground">
              {modelScope ? `Context ready: ${modelScope.comparison_variant || 'model family'}, ${modelScope.comparison_market}, ${modelScope.rival_count} selected competitors. The chat reads the model’s stored evidence and comparisons when you send a request.` : 'The orchestrator chooses which agents to call, reads each result, and decides whether it needs more. Every claim comes with a source.'}
            </p>
          </div>
          <div className="w-full max-w-3xl">{composer}</div>
          <ul className="flex max-w-3xl flex-wrap justify-center gap-2">
            {(modelScope ? ['Where does this model lead or trail the selected competitors?', 'Which comparisons have missing or incompatible evidence?', 'What do customers say about comfort and connectivity?'] : SUGGESTIONS).map((s) => (
              <li key={s}>
                <button type="button" onClick={() => { setText(s); input.current?.focus() }}
                  className="flex items-center gap-2 rounded-2xl border border-border bg-background px-4 py-2.5 text-left text-sm text-foreground/80 transition-colors hover:border-primary/40 hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring">
                  <Globe2 className="size-3.5 shrink-0 text-primary" aria-hidden /> {s}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8">
              {detailLoading && <div className="flex flex-col gap-4" aria-label="Loading conversation"><Skeleton className="ml-auto h-10 w-2/3 rounded-3xl" /><Skeleton className="h-24 w-full rounded-2xl" /></div>}
              {!detailLoading && detail?.messages.map((m) =>
                m.kind === 'step_card' && m.step_id
                  ? <StepCard key={m.id} message={m} step={stepById.get(m.step_id)} />
                  : <Message key={m.id} message={m} findings={findings} />)}
              {working && (
                <div role="status" className="sm:ml-11 flex items-center gap-2.5 text-sm text-muted-foreground">
                  <span className="flex gap-1" aria-hidden>
                    {[0, 1, 2].map((i) => <span key={i} className="typing-dot size-1.5 rounded-full bg-primary" style={{ animationDelay: `${i * 0.15}s` }} />)}
                  </span>
                  <span>{running ? `${running.agent_name} is working. ` : 'The orchestrator is deciding. '}Results appear here as they arrive.</span>
                </div>
              )}
              <div ref={bottom} />
            </div>
          </div>
          <div className={cn('shrink-0 px-4 pb-5 pt-2')}>
            <div className="mx-auto w-full max-w-3xl">{composer}</div>
          </div>
        </>
      )}
    </div>
    </SourceViewerProvider>
  )
}
