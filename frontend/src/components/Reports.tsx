import { DownloadSimple, Printer } from '@phosphor-icons/react'
import { useWorkspace } from '../context'
import { confidenceLabel, dateLabel, downloadFile, formatNumber, portfolioCsv, statusLabel } from '../data'
import { Badge, Button, Empty } from './ui'
import { AcceptedResults, DecisionHistory, SalesTable } from './WorkspaceData'

export function Reports() {
  const { data, line, market, lineLabel, marketLabel, notify } = useWorkspace()
  return <>
    <div className="page-heading no-print"><div><p className="eyebrow">PROGRAMME REPORT</p><h1>A direction worth documenting.</h1><p>Share recorded requirements, research and the reasons behind decisions.</p></div><div className="heading-actions"><Button variant="secondary" disabled={!data.requirements.length} onClick={() => { downloadFile(`programme-${line || 'all'}-${market || 'all'}.csv`, portfolioCsv(data.requirements), 'text/csv;charset=utf-8'); notify('Stored requirement portfolio downloaded with citations.') }}><DownloadSimple size={18} /> Export CSV</Button><Button variant="secondary" onClick={() => downloadFile(`research-${line || 'all'}-${market || 'all'}.json`, JSON.stringify(data.results, null, 2), 'application/json')} disabled={!data.results.length}>Export accepted research</Button><Button onClick={() => window.print()}><Printer size={18} /> Print / save PDF</Button></div></div>
    <article className="programme-report"><header className="report-header"><div><p className="eyebrow">BMW PRODUCT INTELLIGENCE</p><h2>{lineLabel(line)}</h2><p>{marketLabel(market)} / Data read {dateLabel(data.generated_at)}</p></div><Badge>Stored evidence</Badge></header>
      <section><h3>Recorded sales and forecasts</h3><SalesTable /></section>
      <section><h3>Requirement portfolio</h3>{data.requirements.length ? data.requirements.map(r => <div className="report-requirement" key={r.id}><div className="report-requirement-heading"><h4>{r.code || r.id}: {r.title}</h4><Badge>{statusLabel(r.status)}</Badge></div><p>{r.description}</p><dl className="report-facts"><div><dt>Priority score</dt><dd>{r.score === null ? 'Not scored' : formatNumber(r.score)}</dd></div><div><dt>Confidence</dt><dd>{confidenceLabel(r.confidence)}</dd></div><div><dt>Metric</dt><dd>{r.metric || 'Not recorded'}</dd></div><div><dt>Acceptance criteria</dt><dd>{r.acceptance_criteria || 'Not recorded'}</dd></div></dl>{r.assumptions.length > 0 && <p className="report-assumption">Assumptions: {r.assumptions.join('; ')}</p>}{r.uncertainties.length > 0 && <p className="report-assumption">Uncertainties: {r.uncertainties.join('; ')}</p>}<p className="report-citations">Sources: {r.citations.length ? r.citations.map(c => `${c.file} (${c.locator})`).join('; ') : 'No evidence linked.'}</p></div>) : <Empty title="No persisted requirements in this scope">This report contains no requirement rows until they have been stored.</Empty>}</section>
      <section><h3>Accepted agent contributions</h3><AcceptedResults /></section>
      <section><h3>Decision history</h3><DecisionHistory /></section>
      <footer>Requirements, scores, source references and reviews are read from the database. Forecasts retain the source's forecast status.</footer>
    </article>
  </>
}
