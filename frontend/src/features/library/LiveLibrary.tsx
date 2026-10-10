import { useCallback, useEffect, useState } from 'react'
import { Database, Grid3x3, FileText } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import type { Coverage, CoverageCell, SourceInfo } from '@/types/api'
import { contents, fmt } from './format'
import { UploadForm } from './UploadForm'

type Load<T> = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: T }
const THIN = 100 // fewer customer comments than this is shown as thin evidence

const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
const message = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

function CoverageCellView({ cell }: { cell?: CoverageCell }) {
  if (!cell) return <span className="text-muted-foreground">No data</span>
  return (
    <div className="flex flex-col gap-1">
      {cell.feedback === 0 ? (
        <Badge variant="destructive">No customer feedback</Badge>
      ) : cell.feedback < THIN ? (
        <Badge variant="outline">{`Thin: ${fmt(cell.feedback)} comments`}</Badge>
      ) : (
        <span>{`${fmt(cell.feedback)} comments`}</span>
      )}
      <span className="text-muted-foreground">
        {cell.study_cells > 0 ? `${fmt(cell.study_cells)} study cells` : 'No study data'}
      </span>
      <span className="text-muted-foreground">
        {cell.sales_2025 === null ? 'No 2025 sales row' : `2025 sales ${fmt(cell.sales_2025)}`}
      </span>
    </div>
  )
}

export function LiveLibrary() {
  const [sources, setSources] = useState<Load<SourceInfo[]>>({ kind: 'loading' })
  const [coverage, setCoverage] = useState<Load<Coverage>>({ kind: 'loading' })

  // Also called after an upload: the tables then change in place, without going back to the loading state.
  const load = useCallback((signal?: AbortSignal) => {
    api.sources(signal).then((data) => setSources({ kind: 'ok', data }))
      .catch((e) => !aborted(e) && setSources({ kind: 'error', message: message(e) }))
    api.coverage(signal).then((data) => setCoverage({ kind: 'ok', data }))
      .catch((e) => !aborted(e) && setCoverage({ kind: 'error', message: message(e) }))
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    load(ctrl.signal)
    return () => ctrl.abort()
  }, [load])

  const lines = coverage.kind === 'ok' ? [...new Set(coverage.data.cells.map((c) => c.line))] : []
  const loaded = sources.kind === 'ok' ? sources.data.map((s) => s.file) : []

  return (
    <PageShell testId="live-library" title="Sources" Icon={Database} description="What is stored per vehicle line and market. Gaps are shown as gaps.">
      <section aria-labelledby="coverage-h" className="flex flex-col gap-3">
        <h2 id="coverage-h" className="flex items-center gap-2 text-lg"><Grid3x3 className="size-5 text-primary" /> Coverage</h2>
        {coverage.kind === 'loading' && <Skeleton className="h-48 w-full rounded-2xl" aria-label="Loading coverage" />}
        {coverage.kind === 'error' && (
          <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{`Coverage unavailable: ${coverage.message}`}</p>
        )}
        {coverage.kind === 'ok' && (() => {
          const lines = [...new Set(coverage.data.cells.map((c) => c.line))]
          const markets = [...new Set(coverage.data.cells.map((c) => c.market))]
          const cell = (l: string, m: string) => coverage.data.cells.find((c) => c.line === l && c.market === m)
          return (
            <div className="overflow-x-auto rounded-2xl border border-border bg-background shadow-xs" tabIndex={0} role="region" aria-label="Coverage table, scrolls sideways on small screens">
              <table className="w-full min-w-[720px] border-collapse text-sm">
                <caption className="sr-only">Stored evidence by vehicle line and market</caption>
                <thead>
                  <tr className="border-b border-border bg-canvas-tint text-left">
                    <th scope="col" className="p-3 font-semibold">Vehicle line</th>
                    {markets.map((m) => <th key={m} scope="col" className="p-3 font-semibold">{m}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => (
                    <tr key={l} className="border-b border-border align-top">
                      <th scope="row" className="p-3 text-left font-semibold">
                        {l}
                        <span className="block text-xs font-normal text-muted-foreground">
                          {`${fmt(coverage.data.options_by_line[l] ?? 0)} catalog options`}
                        </span>
                      </th>
                      {markets.map((m) => <td key={m} className="p-3"><CoverageCellView cell={cell(l, m)} /></td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })()}
      </section>

      <section aria-labelledby="sources-h" className="flex flex-col gap-3">
        <h2 id="sources-h" className="flex items-center gap-2 text-lg"><FileText className="size-5 text-primary" /> Files</h2>
        <UploadForm lines={lines} loaded={loaded} onStored={load} />
        {sources.kind === 'loading' && <Skeleton className="h-40 w-full rounded-2xl" aria-label="Loading sources" />}
        {sources.kind === 'error' && (
          <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{`Sources unavailable: ${sources.message}`}</p>
        )}
        {sources.kind === 'ok' && sources.data.length === 0 && (
          <p className="text-muted-foreground">No source files are loaded yet.</p>
        )}
        {sources.kind === 'ok' && sources.data.length > 0 && (
          <div className="overflow-x-auto rounded-2xl border border-border bg-background shadow-xs" tabIndex={0} role="region" aria-label="Sources table, scrolls sideways on small screens">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <caption className="sr-only">Source files loaded into the evidence store</caption>
              <thead>
                <tr className="border-b border-border bg-canvas-tint text-left">
                  <th scope="col" className="p-3 font-semibold">File</th>
                  <th scope="col" className="p-3 font-semibold">Kind</th>
                  <th scope="col" className="p-3 font-semibold">Line</th>
                  <th scope="col" className="p-3 font-semibold">Contents</th>
                </tr>
              </thead>
              <tbody>
                {sources.data.map((s) => (
                  <tr key={s.id} className="border-b border-border align-top">
                    <th scope="row" className="p-3 text-left font-semibold">{s.file}</th>
                    <td className="p-3">{s.family}</td>
                    <td className="p-3">{s.vehicle_line ?? 'Several'}</td>
                    <td className="p-3">{contents(s.counts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </PageShell>
  )
}
