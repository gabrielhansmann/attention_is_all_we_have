import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { api, ApiError } from '@/lib/api'
import { LINE_LABELS, MARKET_LABELS } from '@/lib/live'
import { cn } from '@/lib/utils'
import type { AgentInfo, ChatMessage, Conversation, ConversationDetail, Run } from '@/types/api'

const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

interface PlanStepView {
  position: number
  agent: string
  stage: number
  reason: string | null
  available: boolean
}

/** Read the structured plan the backend stored with a plan message, tolerating anything unexpected. */
function planSteps(m: ChatMessage): PlanStepView[] {
  const raw = m.payload.steps
  if (!Array.isArray(raw)) return []
  return raw.flatMap((s) => {
    if (typeof s !== 'object' || s === null) return []
    const r = s as Record<string, unknown>
    if (typeof r.agent !== 'string') return []
    return [{
      position: typeof r.position === 'number' ? r.position : 0,
      agent: r.agent,
      stage: typeof r.stage === 'number' ? r.stage : 0,
      reason: typeof r.reason === 'string' && r.reason ? r.reason : null,
      available: r.available === true,
    }]
  })
}

function PlanCard({ message, canEdit, superseded, onEdit }: { message: ChatMessage; canEdit: boolean; superseded: boolean; onEdit: () => void }) {
  const steps = planSteps(message)
  const line = String(message.payload.vehicle_line ?? 'ALL')
  const market = String(message.payload.market ?? 'ALL')
  const removed = Array.isArray(message.payload.removed) ? (message.payload.removed as string[]) : []
  const added = Array.isArray(message.payload.added) ? (message.payload.added as string[]) : []
  return (
    <article className="flex flex-col gap-3 border border-border bg-background p-5" aria-label={message.kind === 'plan' ? 'Plan' : 'Updated plan'}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base">{message.kind === 'plan' ? 'Plan' : 'Plan updated'}</h3>
        <Badge variant="outline">{LINE_LABELS[line] ?? line}</Badge>
        <Badge variant="outline">{MARKET_LABELS[market] ?? market}</Badge>
        {superseded && <Badge variant="secondary">Replaced by a later plan</Badge>}
      </div>
      {message.kind === 'plan_change' && (removed.length > 0 || added.length > 0) && (
        <p className="text-sm text-muted-foreground">
          {[removed.length > 0 && `Removed ${removed.join(', ')}`, added.length > 0 && `Added ${added.join(', ')}`].filter(Boolean).join('. ')}
        </p>
      )}
      {steps.length === 0 ? (
        <p className="whitespace-pre-line text-sm">{message.content}</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {steps.map((s) => (
            <li key={s.agent} className="flex gap-3">
              <span className="w-6 shrink-0 font-bold tabular-nums">{s.position}.</span>
              <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-bold">{s.agent}</span>
                  {!s.available && <Badge variant="outline">Not built yet</Badge>}
                </div>
                {s.reason && <span className="text-sm text-muted-foreground">{s.reason}</span>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {canEdit && (
        <div>
          <Button variant="outline" onClick={onEdit}>Edit plan</Button>
        </div>
      )}
    </article>
  )
}

function PlanEditor({ run, agents, onSaved, onCancel }: {
  run: Run
  agents: AgentInfo[]
  onSaved: (detail: ConversationDetail | null) => void
  onCancel: () => void
}) {
  const current = run.steps.map((s) => s.agent_name)
  const [picked, setPicked] = useState<string[]>(current)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const changed = picked.length !== current.length || picked.some((a) => !current.includes(a))

  function toggle(name: string) {
    setPicked((p) => (p.includes(name) ? p.filter((n) => n !== name) : [...p, name]))
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.editPlan(run.id, picked)
      onSaved(run.conversation_id ? await api.conversation(run.conversation_id) : null)
    } catch (err) {
      setError(errorText(err))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} className="flex flex-col gap-4 border border-primary p-5" aria-label="Edit plan">
      <fieldset className="flex flex-col gap-3">
        <legend className="text-base font-bold">Choose the agents for this plan</legend>
        <p className="text-sm text-muted-foreground">
          Agents run in pipeline order, one at a time. A later stage needs an agent from each earlier stage.
        </p>
        {agents.map((a) => (
          <label key={a.name} className="flex cursor-pointer items-start gap-3">
            <input type="checkbox" className="mt-1 size-4 accent-primary" checked={picked.includes(a.name)}
              onChange={() => toggle(a.name)} />
            <span className="flex flex-col">
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-bold">{a.name}</span>
                {!a.available && <Badge variant="outline">Not built yet</Badge>}
              </span>
              <span className="text-sm text-muted-foreground">{a.description}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-3">
        <Button type="submit" disabled={!changed || saving || picked.length === 0}>{saving ? 'Saving' : 'Save plan'}</Button>
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  const mine = message.role === 'pm'
  return (
    <div className={cn('flex flex-col gap-1 border p-4', mine ? 'border-border bg-muted' : 'border-border bg-background')}>
      <span className="text-xs tracking-wide text-muted-foreground">{mine ? 'You' : 'Orchestrator'}</span>
      <p className="whitespace-pre-line text-sm">{message.content}</p>
    </div>
  )
}

export function LiveResearch() {
  const [list, setList] = useState<Conversation[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [text, setText] = useState('')
  const [planning, setPlanning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)

  const refreshList = useCallback((signal?: AbortSignal) =>
    api.conversations(signal).then((c) => { setList(c); setListError(null) })
      .catch((e) => !aborted(e) && setListError(errorText(e))), [])

  useEffect(() => {
    const ctrl = new AbortController()
    refreshList(ctrl.signal)
    api.agents(ctrl.signal).then(setAgents).catch(() => undefined)
    return () => ctrl.abort()
  }, [refreshList])

  function open(id: string) {
    setDetailLoading(true)
    setEditing(null)
    setError(null)
    api.conversation(id)
      .then(setDetail)
      .catch((e) => setError(errorText(e)))
      .finally(() => setDetailLoading(false))
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    const content = text.trim()
    if (content.length < 3 || planning) return
    setPlanning(true)
    setError(null)
    try {
      if (detail) {
        await api.postRequest(detail.conversation.id, content)
        setDetail(await api.conversation(detail.conversation.id))
      } else {
        setDetail(await api.createConversation(content))
      }
      setText('')
      refreshList()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setPlanning(false)
    }
  }

  const latestPlanMessage = new Map<string, string>() // run id -> id of its newest plan or plan_change message
  for (const m of detail?.messages ?? []) {
    if ((m.kind === 'plan' || m.kind === 'plan_change') && m.run_id) latestPlanMessage.set(m.run_id, m.id)
  }
  const runById = new Map((detail?.runs ?? []).map((r) => [r.id, r]))

  return (
    <div className="flex flex-col gap-6" data-testid="live-research">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-muted-foreground">
          This view talks to the backend. The orchestrator reads your request, chooses the agents it needs and
          shows its plan. Agents do not run yet: starting a plan and the review steps (accept, edit, retry,
          reject) arrive with the first agent.
        </p>
        <HealthBadge />
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <aside aria-labelledby="live-conv-h" className="flex flex-col gap-3 self-start border border-border p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 id="live-conv-h" className="text-base">Conversations</h2>
            <Button variant="outline" size="sm" onClick={() => { setDetail(null); setEditing(null); setError(null) }}>
              New
            </Button>
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
          <h2 id="live-thread-h" className="text-xl">{detail ? detail.conversation.title : 'Start a research request'}</h2>
          {detailLoading && <Skeleton className="h-32 w-full" aria-label="Loading conversation" />}
          {!detailLoading && detail?.messages.length === 0 && (
            <p className="text-muted-foreground">This conversation has no messages yet.</p>
          )}
          {!detailLoading && detail?.messages.map((m) => {
            if ((m.kind === 'plan' || m.kind === 'plan_change') && m.run_id) {
              const run = runById.get(m.run_id)
              const newest = latestPlanMessage.get(m.run_id) === m.id
              const editable = !!run && run.steps.every((s) => s.status === 'planned')
              return (
                <div key={m.id} className="flex flex-col gap-3">
                  <PlanCard message={m} superseded={!newest} canEdit={newest && editable && editing !== run?.id}
                    onEdit={() => run && setEditing(run.id)} />
                  {newest && run && editing === run.id && (
                    <PlanEditor run={run} agents={agents} onCancel={() => setEditing(null)}
                      onSaved={(d) => { if (d) setDetail(d); setEditing(null) }} />
                  )}
                </div>
              )
            }
            return <Bubble key={m.id} message={m} />
          })}

          <form onSubmit={send} className="flex flex-col gap-3 border border-border p-5">
            <Label htmlFor="live-request">{detail ? 'Follow-up request' : 'Research request'}</Label>
            <Textarea id="live-request" rows={3} value={text} onChange={(e) => setText(e.target.value)}
              placeholder="For example: What do US G60 owners dislike most about the infotainment?" />
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div>
              <Button type="submit" size="lg" disabled={text.trim().length < 3 || planning}>
                {planning ? 'Planning' : 'Plan request'}
              </Button>
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
