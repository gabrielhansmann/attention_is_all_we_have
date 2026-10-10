import { useState } from 'react'
import { Check, Copy, FileText } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Prose } from '@/features/sources/Prose'
import { SourceViewerProvider } from '@/features/sources/SourceViewer'
import { findingsFrom, indexOf } from '@/features/sources/citations'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Dossier } from '@/types/api'
import { ProcessStrip, useLoad } from './shared'

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString('en-GB', { dateStyle: 'medium' }) : '')

export function DossiersPage() {
  const [state] = useLoad<Dossier[]>((s) => api.dossiers(s))
  const [pick, setPick] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const list = state.kind === 'ok' ? state.data : []
  const open = list.find((d) => d.run_id === pick) ?? list[0]

  const copy = async () => {
    try { await navigator.clipboard.writeText(open!.dossier); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* clipboard blocked */ }
  }

  return (
    <SourceViewerProvider>
      <PageShell testId="dossiers" Icon={FileText} title="Dossiers"
        description="One dossier per research run.">
        <ProcessStrip current="dossiers" counts={state.kind === 'ok' ? { dossiers: list.length } : undefined} />
        {state.kind === 'loading' && <Skeleton className="h-64 w-full rounded-2xl" aria-label="Loading dossiers" />}
        {state.kind === 'error' && <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{`Dossiers unavailable: ${state.message}`}</p>}
        {state.kind === 'ok' && list.length === 0 && (
          <section className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-border bg-card p-6">
            <h2 className="text-lg">No dossiers yet</h2>
            <p className="max-w-xl text-sm text-muted-foreground">A dossier is written when a research run ends with documentation. Ask the research chat to document its result, for example: &ldquo;...and write the dossier.&rdquo;</p>
            <a href="#research" className="inline-flex h-10 items-center rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground shadow-sm">Go to research</a>
          </section>
        )}
        {open && (
          <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
            <nav aria-label="Dossiers" className="flex flex-col gap-1.5">
              {list.map((d) => (
                <button key={d.run_id} type="button" onClick={() => setPick(d.run_id)} aria-current={d.run_id === open.run_id ? 'true' : undefined}
                  className={cn('rounded-xl border px-3 py-2 text-left text-sm focus-visible:outline-2 focus-visible:outline-ring', d.run_id === open.run_id ? 'border-primary bg-accent' : 'border-border bg-card hover:bg-muted')}>
                  <span className="line-clamp-2 font-medium">{d.title}</span>
                  <span className="text-xs text-muted-foreground">{`${d.vehicle_line === 'ALL' ? 'All lines' : d.vehicle_line} · ${d.market === 'ALL' ? 'All markets' : d.market} · ${when(d.created_at)}`}</span>
                </button>
              ))}
            </nav>
            <article aria-label="Dossier" className="rounded-2xl border border-border bg-card p-5 shadow-xs">
              <div className="mb-3 flex justify-end"><Button variant="outline" onClick={copy}>{copied ? <Check aria-hidden /> : <Copy aria-hidden />} {copied ? 'Copied' : 'Copy as Markdown'}</Button></div>
              <Prose text={open.dossier} findings={indexOf(findingsFrom(open.findings))} collapse={['Accepted steps', 'Audit trail']} />
            </article>
          </div>
        )}
      </PageShell>
    </SourceViewerProvider>
  )
}
