import { Badge } from '@/components/ui/badge'
import type { Coverage, CoverageCell } from '@/types/api'
import { fmt } from './format'

export const THIN = 100 // fewer customer comments than this is shown as thin evidence

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

/** What is stored per vehicle line and market. A gap is shown as a gap, not as a missing cell. */
export function CoverageTab({ coverage }: { coverage: Coverage }) {
  const lines = [...new Set(coverage.cells.map((c) => c.line))]
  const markets = [...new Set(coverage.cells.map((c) => c.market))]
  const cell = (l: string, m: string) => coverage.cells.find((c) => c.line === l && c.market === m)
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
            <tr key={l} className="border-b border-border align-top last:border-b-0">
              <th scope="row" className="p-3 text-left font-semibold">
                {l}
                <span className="block text-xs font-normal text-muted-foreground">
                  {`${fmt(coverage.options_by_line[l] ?? 0)} catalog options`}
                </span>
              </th>
              {markets.map((m) => <td key={m} className="p-3"><CoverageCellView cell={cell(l, m)} /></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
