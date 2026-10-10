import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import { useWorkspace } from '@/context'
import type { Coverage, CoverageCell, SourceInfo } from '@/types/api'

type Load<T> = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: T }

const fmt = (n: number) => n.toLocaleString('en-US')
const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
const message = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

function contents(c: SourceInfo['counts']): string {
  const parts = [
    c.feedback && `${fmt(c.feedback)} comments`,
    c.pdf_chunks && `${fmt(c.pdf_chunks)} text passages`,
    c.options && `${fmt(c.options)} equipment options`,
    c.study_cells && `${fmt(c.study_cells)} study cells`,
    c.sales_rows && `${fmt(c.sales_rows)} sales rows`,
    c.findings && `${fmt(c.findings)} findings`,
  ].filter(Boolean)
  return parts.join(', ') || 'Nothing extracted'
}

function CoverageCellView({ cell, salesYear }: { cell?: CoverageCell; salesYear: number | null }) {
  if (!cell) return <span className="text-muted-foreground">No data</span>
  return (
    <div className="flex flex-col gap-1">
      {cell.feedback === 0 ? (
        <Badge variant="destructive">No customer feedback</Badge>
      ) : (
        <span>{`${fmt(cell.feedback)} comments`}</span>
      )}
      <span className="text-muted-foreground">
        {cell.study_cells > 0 ? `${fmt(cell.study_cells)} study cells` : 'No study data'}
      </span>
      <span className="text-muted-foreground">
        {salesYear === null ? 'No recorded sales year' : cell.sales_volume === null ? `No ${salesYear} sales row` : `${salesYear} sales ${fmt(cell.sales_volume)}`}
      </span>
    </div>
  )
}

export function LiveLibrary() {
  const { lineLabel, marketLabel } = useWorkspace()
  const [sources, setSources] = useState<Load<SourceInfo[]>>({ kind: 'loading' })
  const [coverage, setCoverage] = useState<Load<Coverage>>({ kind: 'loading' })

  useEffect(() => {
    const ctrl = new AbortController()
    api.sources(ctrl.signal).then((data) => setSources({ kind: 'ok', data }))
      .catch((e) => !aborted(e) && setSources({ kind: 'error', message: message(e) }))
    api.coverage(ctrl.signal).then((data) => setCoverage({ kind: 'ok', data }))
      .catch((e) => !aborted(e) && setCoverage({ kind: 'error', message: message(e) }))
    return () => ctrl.abort()
  }, [])

  return (
    <div className="flex flex-col gap-8" data-testid="live-library">
      <section aria-labelledby="coverage-h" className="flex flex-col gap-3">
        <h2 id="coverage-h" className="text-xl">Evidence coverage</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          What is stored per vehicle line and market. Empty cells show missing evidence.
          Sales use the latest recorded year; forecasts are excluded from these counts.
        </p>
        {coverage.kind === 'loading' && <Skeleton className="h-48 w-full" aria-label="Loading coverage" />}
        {coverage.kind === 'error' && (
          <p role="alert" className="border border-destructive p-4 text-destructive">{`Coverage unavailable: ${coverage.message}`}</p>
        )}
        {coverage.kind === 'ok' && (() => {
          const lines = [...new Set(coverage.data.cells.map((c) => c.line))]
          const markets = [...new Set(coverage.data.cells.map((c) => c.market))]
          const cell = (l: string, m: string) => coverage.data.cells.find((c) => c.line === l && c.market === m)
          return (
            <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Coverage table, scrolls sideways on small screens">
              <table className="w-full min-w-[720px] border-collapse text-sm">
                <caption className="sr-only">Stored evidence by vehicle line and market</caption>
                <thead>
                  <tr className="border-b border-border text-left">
                    <th scope="col" className="p-3 font-bold">Vehicle line</th>
                    {markets.map((m) => <th key={m} scope="col" className="p-3 font-bold">{marketLabel(m)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {lines.map((l) => (
                    <tr key={l} className="border-b border-border align-top">
                      <th scope="row" className="p-3 text-left font-bold">
                        {lineLabel(l)}
                        <span className="block text-xs font-normal text-muted-foreground">
                          {`${fmt(coverage.data.options_by_line[l] ?? 0)} catalog options`}
                        </span>
                      </th>
                      {markets.map((m) => <td key={m} className="p-3"><CoverageCellView cell={cell(l, m)} salesYear={coverage.data.sales_year} /></td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })()}
      </section>

      <section aria-labelledby="sources-h" className="flex flex-col gap-3">
        <h2 id="sources-h" className="text-xl">Loaded source files</h2>
        {sources.kind === 'loading' && <Skeleton className="h-40 w-full" aria-label="Loading sources" />}
        {sources.kind === 'error' && (
          <p role="alert" className="border border-destructive p-4 text-destructive">{`Sources unavailable: ${sources.message}`}</p>
        )}
        {sources.kind === 'ok' && sources.data.length === 0 && (
          <p className="text-muted-foreground">No source files are loaded yet.</p>
        )}
        {sources.kind === 'ok' && sources.data.length > 0 && (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Sources table, scrolls sideways on small screens">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <caption className="sr-only">Source files loaded into the evidence store</caption>
              <thead>
                <tr className="border-b border-border text-left">
                  <th scope="col" className="p-3 font-bold">File</th>
                  <th scope="col" className="p-3 font-bold">Kind</th>
                  <th scope="col" className="p-3 font-bold">Line</th>
                  <th scope="col" className="p-3 font-bold">Contents</th>
                </tr>
              </thead>
              <tbody>
                {sources.data.map((s) => (
                  <tr key={s.id} className="border-b border-border align-top">
                    <th scope="row" className="p-3 text-left font-bold">{/^https?:\/\//i.test(s.file) ? <a href={s.file} target="_blank" rel="noreferrer">{s.title || s.file}</a> : s.file}</th>
                    <td className="p-3">{s.family}</td>
                    <td className="p-3">{s.vehicle_line ? lineLabel(s.vehicle_line) : 'Scope not specified'}</td>
                    <td className="p-3">{contents(s.counts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
