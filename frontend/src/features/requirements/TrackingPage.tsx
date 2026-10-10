import { useState } from 'react'
import { AlertTriangle, CheckCircle2, Radar, RefreshCw, Sparkles, Hourglass, Swords, type LucideIcon } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { CitationChip } from '@/features/sources/CitationChip'
import { SourceViewerProvider } from '@/features/sources/SourceViewer'
import { api } from '@/lib/api'
import type { DecisionAction, Requirement, TrackingFlag, TrackingResult, TrackingState } from '@/types/api'
import { Cited, DecisionButtons, ProcessStrip, messageOf, useLoad } from './shared'

const FLAG: Record<TrackingFlag['flag_type'], { label: string; Icon: LucideIcon; help: string }> = {
  new_evidence: { label: 'New evidence', Icon: Sparkles, help: 'Fresh feedback supports this requirement.' },
  contradicting: { label: 'Contradicting', Icon: Swords, help: 'Fresh feedback points the other way.' },
  stale: { label: 'Stale', Icon: Hourglass, help: 'The evidence is old.' },
}

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : 'never')

function TrackedCard({ req, onDecide }: { req: Requirement; onDecide: (id: string, a: DecisionAction, note?: string) => Promise<void> }) {
  const attention = req.flags.length > 0
  return (
    <article data-testid="tracked" aria-label={`${req.code} ${req.title}`}
      className={`flex flex-col gap-3 rounded-2xl border bg-card p-5 shadow-xs ${attention ? 'border-primary' : 'border-border'}`}>
      <header className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{`${req.code} · ${req.vehicle_line === 'ALL' ? 'All lines' : req.vehicle_line} · tracked since ${when(req.tracked_at)}`}</p>
          <h2 className="mt-0.5 text-lg">{req.title}</h2>
        </div>
        {attention
          ? <Badge><AlertTriangle aria-hidden /> {`${req.flags.length} to review`}</Badge>
          : <Badge variant="outline"><CheckCircle2 aria-hidden /> No change</Badge>}
      </header>
      {req.payload.metric && <p className="text-sm"><span className="font-medium">Target: </span><Cited statement={req.payload.metric} req={req} /></p>}
      {attention && (
        <ul className="flex flex-col gap-2">
          {req.flags.map((f, i) => {
            const { label, Icon, help } = FLAG[f.flag_type] ?? FLAG.new_evidence
            return (
              <li key={i} className="flex items-start gap-2 rounded-xl bg-canvas-tint p-3 text-sm">
                <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                <div className="min-w-0">
                  <p><span className="font-medium">{label}. </span>{f.reason}</p>
                  <p className="text-xs text-muted-foreground">{`${help} Found ${when(f.detected_at)}.`}
                    {f.citations.filter((c) => c.source && c.locator).slice(0, 3).map((c, j) => <CitationChip key={j} n={j + 1} sourceRef={{ file: c.source!, locator: c.locator! }} />)}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <DecisionButtons req={req} only={attention ? ['acknowledge', 'challenge', 'supersede'] : ['supersede']} onDecide={onDecide} />
    </article>
  )
}

export function TrackingPage() {
  const [state, reload] = useLoad<TrackingState>((s) => api.tracking(s))
  const [checking, setChecking] = useState(false)
  const [result, setResult] = useState<TrackingResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const check = async () => {
    setChecking(true); setError(null)
    try { setResult(await api.checkTracking()); reload() } catch (e) { setError(messageOf(e)) } finally { setChecking(false) }
  }
  const decide = async (id: string, action: DecisionAction, note?: string) => { await api.decide(id, action, note); reload() }
  const reqs = state.kind === 'ok' ? state.data.requirements : []
  const flagged = reqs.filter((r) => r.flags.length).length

  return (
    <SourceViewerProvider>
      <PageShell testId="tracking" Icon={Radar} title="Tracking"
        description="Approved requirements stay under watch for about two years. Check for new customer evidence and decide what to do about each change.">
        <ProcessStrip current="tracking" counts={{ flags: flagged }} />
        {state.kind === 'loading' && <Skeleton className="h-48 w-full rounded-2xl" aria-label="Loading tracking" />}
        {state.kind === 'error' && <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{`Tracking unavailable: ${state.message}`}</p>}
        {state.kind === 'ok' && reqs.length === 0 && (
          <section className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-border bg-card p-6">
            <h2 className="text-lg">Nothing is tracked yet</h2>
            <p className="max-w-xl text-sm text-muted-foreground">Approve a requirement and it appears here. Then you can check it against new evidence.</p>
            <a href="#requirements" className="inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm">Review requirements</a>
          </section>
        )}
        {state.kind === 'ok' && reqs.length > 0 && (
          <>
            <section aria-label="Check" className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card p-4 shadow-xs">
              <Button size="lg" className="rounded-xl shadow-sm" disabled={checking} onClick={check}><RefreshCw className={checking ? 'animate-spin' : ''} aria-hidden /> {checking ? 'Checking…' : 'Check for new evidence'}</Button>
              <p className="text-sm text-muted-foreground">{`Last checked: ${when(state.data.last_checked)}. ${flagged ? `${flagged} requirement${flagged === 1 ? ' needs' : 's need'} your attention.` : 'Nothing needs attention.'}`}</p>
              {error && <p role="alert" className="w-full text-sm text-destructive">{error}</p>}
              {result && !error && <p role="status" className="w-full text-sm">{result.errors.length ? `Checked ${result.checked}. ${result.errors.join(' ')}` : `Checked ${result.checked} requirement${result.checked === 1 ? '' : 's'}: ${result.flags.length} change${result.flags.length === 1 ? '' : 's'} found.`}</p>}
            </section>
            {reqs.map((r) => <TrackedCard key={r.id} req={r} onDecide={decide} />)}
          </>
        )}
      </PageShell>
    </SourceViewerProvider>
  )
}
