import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ClipboardCheck, Search } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SourceViewerProvider } from '@/features/sources/SourceViewer'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { DecisionAction, Requirement, RequirementList, RequirementStatus } from '@/types/api'
import { PrioritiesView } from './PrioritiesView'
import { Cited, DecisionButtons, ProcessStrip, StatusBadge, pct, tierShort, useLoad } from './shared'

const FILTERS: { id: 'review' | RequirementStatus | 'all'; label: string; match: (s: RequirementStatus) => boolean }[] = [
  { id: 'review', label: 'Needs review', match: (s) => s === 'draft' || s === 'pm_review' },
  { id: 'tracked', label: 'Tracked', match: (s) => s === 'tracked' },
  { id: 'challenged', label: 'Challenged', match: (s) => s === 'challenged' },
  { id: 'rejected', label: 'Rejected', match: (s) => s === 'rejected' || s === 'superseded' },
  { id: 'all', label: 'All', match: () => true },
]

const tabFromHash = () => (window.location.hash.includes('tab=priorities') ? 'priorities' : 'review')

function Bar({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="flex items-center gap-2 text-xs" title={hint}>
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${label} ${pct(value)}`}>
        <span className="block h-full rounded-full bg-primary" style={{ width: pct(value) }} />
      </span>
      <span className="w-9 text-right tabular-nums">{pct(value)}</span>
    </div>
  )
}

export function RequirementCard({ req, onDecide }: { req: Requirement; onDecide: (id: string, a: DecisionAction, note?: string) => Promise<void> }) {
  const p = req.payload
  const [more, setMore] = useState(false)
  const caveats = [...(p.assumptions ?? []).map((t) => ['Assumption', t]), ...(p.uncertainties ?? []).map((t) => ['Uncertain', t])]
  return (
    <article data-testid="requirement" aria-label={`${req.code} ${req.title}`} className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-xs">
      <header className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{`${req.code} · ${req.vehicle_line === 'ALL' ? 'All lines' : req.vehicle_line} · ${req.market === 'ALL' ? 'All markets' : req.market}${p.domain_label ? ` · ${p.domain_label}` : ''}`}</p>
          <h2 className="mt-0.5 text-lg">{req.title}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={req.status} />
          {req.score && <Badge variant="secondary" title={req.score.proposed_tier}>{`${tierShort(req.score.proposed_tier)} · ${req.score.composite.toFixed(2)}`}</Badge>}
          <Badge variant="outline">{p.evidence_level}</Badge>
        </div>
      </header>

      <p className="text-[0.95rem] leading-relaxed"><Cited statement={p.description} req={req} /></p>

      <div className="grid gap-3 sm:grid-cols-2">
        <section aria-label="Target" className="rounded-xl bg-canvas-tint p-3">
          <h3 className="text-sm">Target</h3>
          <p className="mt-1 text-sm">{p.metric ? <Cited statement={p.metric} req={req} /> : 'No target yet. Set one before this goes to tracking.'}</p>
        </section>
        <section aria-label="Acceptance criteria" className="rounded-xl bg-canvas-tint p-3">
          <h3 className="text-sm">Acceptance criteria</h3>
          {p.acceptance_criteria.length ? (
            <ul className="mt-1 flex flex-col gap-1 text-sm">
              {p.acceptance_criteria.map((c, i) => <li key={i} className="pl-4 -indent-3">{'• '}<Cited statement={c} req={req} /></li>)}
            </ul>
          ) : <p className="mt-1 text-sm text-muted-foreground">None yet.</p>}
        </section>
      </div>

      {req.score && (
        <section aria-label="Priority" className="flex flex-col gap-1.5">
          <Bar label="Customer" value={req.score.customer_relevance} hint="How strongly customers ask for this" />
          <Bar label="Business" value={req.score.business_signal} hint="Sales and competitor signal" />
        </section>
      )}

      {(caveats.length > 0 || req.score?.rationale || req.decision_note) && (
        <div>
          <button type="button" aria-expanded={more} onClick={() => setMore(!more)} className="flex items-center gap-1 text-sm font-medium text-primary focus-visible:outline-2 focus-visible:outline-ring">
            <ChevronDown className={cn('size-4 transition-transform', more && 'rotate-180')} aria-hidden /> {more ? 'Hide details' : 'Why this score, and what is uncertain'}
          </button>
          {more && (
            <div className="mt-2 flex flex-col gap-2 text-sm">
              {req.score?.rationale && <p>{req.score.rationale}</p>}
              {caveats.map(([k, t], i) => <p key={i} className="text-muted-foreground"><span className="font-medium text-foreground">{k}: </span>{t}</p>)}
              {req.decision_note && <p className="text-muted-foreground"><span className="font-medium text-foreground">{`${req.decided_by ?? 'PM'} decided: `}</span>{req.decision_note}</p>}
            </div>
          )}
        </div>
      )}

      {req.actions.length > 0 && <DecisionButtons req={req} only={['approve', 'challenge', 'reject', 'reopen']} onDecide={onDecide} />}
    </article>
  )
}

export function RequirementsPage() {
  const [state, reload] = useLoad<RequirementList>((s) => api.requirements(undefined, s))
  const [filter, setFilter] = useState<(typeof FILTERS)[number]['id']>('review')
  const [tab, setTab] = useState(tabFromHash)

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const decide = async (id: string, action: DecisionAction, note?: string) => { await api.decide(id, action, note); reload() }

  const all = state.kind === 'ok' ? state.data.requirements : []
  const review = all.filter((r) => r.status === 'draft' || r.status === 'pm_review').length
  // First visit with nothing waiting: show everything instead of an empty "Needs review" list.
  useEffect(() => { if (state.kind === 'ok' && review === 0 && all.length > 0) setFilter((f) => (f === 'review' ? 'all' : f)) }, [state.kind, review, all.length])
  const shown = useMemo(() => all.filter((r) => FILTERS.find((f) => f.id === filter)!.match(r.status)), [all, filter])

  return (
    <SourceViewerProvider>
      <PageShell testId="requirements" Icon={ClipboardCheck} title="Requirements"
        description="Decide which drafted requirements are worth tracking.">
        <ProcessStrip current={tab === 'priorities' ? 'priorities' : 'requirements'} counts={{ review }} />
        {state.kind === 'loading' && <div className="flex flex-col gap-4"><Skeleton className="h-56 w-full rounded-2xl" aria-label="Loading requirements" /><Skeleton className="h-56 w-full rounded-2xl" /></div>}
        {state.kind === 'error' && <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{`Requirements unavailable: ${state.message}`}</p>}
        {state.kind === 'ok' && all.length === 0 && (
          <section className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-border bg-card p-6">
            <h2 className="text-lg">No requirements yet</h2>
            <p className="max-w-xl text-sm text-muted-foreground">Ask the research chat to derive requirements, for example: &ldquo;Derive requirements for the G60 successor in the US from customer feedback and rank them.&rdquo; Finished runs file their requirements here.</p>
            <a href="#research" className="inline-flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm"><Search className="size-4" aria-hidden /> Start a research request</a>
          </section>
        )}
        {state.kind === 'ok' && all.length > 0 && (
          <Tabs value={tab} onValueChange={(v) => { setTab(String(v)); window.history.replaceState(null, '', v === 'priorities' ? '#requirements?tab=priorities' : '#requirements') }}>
            <TabsList className="h-10 rounded-xl p-1">
              <TabsTrigger value="review" className="px-4 text-foreground">Review</TabsTrigger>
              <TabsTrigger value="priorities" className="px-4 text-foreground">Priorities</TabsTrigger>
            </TabsList>
            <TabsContent value="review" className="mt-3 flex flex-col gap-4">
              <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
                {FILTERS.map((f) => {
                  const n = all.filter((r) => f.match(r.status)).length
                  return (
                    <button key={f.id} type="button" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}
                      className={cn('h-9 rounded-full border px-3.5 text-sm focus-visible:outline-2 focus-visible:outline-ring', filter === f.id ? 'border-primary bg-accent font-medium text-accent-foreground' : 'border-border bg-card text-muted-foreground hover:text-foreground')}>
                      {`${f.label} (${n})`}
                    </button>
                  )
                })}
              </div>
              {shown.length === 0 && <p className="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">Nothing here. Switch the filter above.</p>}
              {shown.map((r) => <RequirementCard key={r.id} req={r} onDecide={decide} />)}
            </TabsContent>
            <TabsContent value="priorities" className="mt-3"><PrioritiesView requirements={all} /></TabsContent>
          </Tabs>
        )}
      </PageShell>
    </SourceViewerProvider>
  )
}
