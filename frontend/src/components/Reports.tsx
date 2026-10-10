import { DownloadSimple, Printer } from '@phosphor-icons/react'
import { useWorkspace } from '../context'
import { composite, dateLabel, downloadFile, lineNames, marketNames, portfolioCsv, statusNames, tier } from '../data'
import { Badge, Button, Empty } from './ui'

export function Reports() {
  const { workspace, line, market, requirements, metrics, audits, notify } = useWorkspace()
  return <>
    <div className="page-heading no-print"><div><p className="eyebrow">PROGRAMME REPORT</p><h1>A direction worth documenting.</h1><p>Share the current targets, requirements, and reasons behind them.</p></div><div className="heading-actions"><Button variant="secondary" disabled={!requirements.length} onClick={() => { downloadFile(`programme-${line}-${market}.csv`, portfolioCsv(requirements, workspace.weights, workspace.sources), 'text/csv;charset=utf-8'); notify('Programme portfolio downloaded with citations.') }}><DownloadSimple size={18} /> Export CSV</Button><Button onClick={() => window.print()}><Printer size={18} /> Print / save PDF</Button></div></div>
    <article className="programme-report"><header className="report-header"><div><p className="eyebrow">BMW PRODUCT INTELLIGENCE</p><h2>{lineNames[line]} successor programme</h2><p>{line} · {marketNames[market]} · Generated {dateLabel(new Date().toISOString())}</p></div><Badge>Illustrative programme</Badge></header>
      <div className="report-note">This report includes sample evidence and locally saved PM decisions. It does not represent validated BMW specifications or live competitor research.</div>
      <section><h3>Successor direction</h3><div className="table-scroll" role="region" aria-label="Successor direction" tabIndex={0}><table><thead><tr><th scope="col">Aspect</th><th scope="col">Baseline</th><th scope="col">Target</th><th scope="col">Unit</th></tr></thead><tbody>{metrics.map(m => <tr key={m.id}><td>{m.label}</td><td>{m.baseline}</td><td>{m.target}</td><td>{m.unit}</td></tr>)}</tbody></table></div></section>
      <section><h3>Requirement portfolio</h3>{requirements.length ? requirements.map(r => <div className="report-requirement" key={r.id}><div className="report-requirement-heading"><h4>{r.id}: {r.title}</h4><Badge>{statusNames[r.status]}</Badge></div><p>{r.description}</p><dl className="report-facts"><div><dt>Priority</dt><dd>{tier(composite(r, workspace.weights))}, score {composite(r, workspace.weights).toFixed(2)}</dd></div><div><dt>Confidence</dt><dd>{r.confidence}%</dd></div><div><dt>Target</dt><dd>{r.metric}</dd></div><div><dt>Acceptance</dt><dd>{r.acceptance}</dd></div></dl><p className="report-assumption">Assumption: {r.assumption}</p><p className="report-citations">Sources: {r.sourceIds.map(id => { const s = workspace.sources.find(x => x.id === id); return s ? `${s.name} (${s.locator})` : id }).join('; ')}</p></div>) : <Empty title="No requirements yet">Start a research run to create the first draft.</Empty>}</section>
      <section><h3>Decision history</h3>{audits.length ? audits.map(a => <div className="report-audit" key={a.id}><strong>{a.title}</strong><p>{a.detail}</p><small>{a.actor} · {dateLabel(a.time)}</small></div>) : <p>No decisions have been recorded in this scope.</p>}</section>
      <footer>All sources remain attached to their requirements. Customer relevance, business signal, strategic fit, and effort are scored separately from confidence.</footer>
    </article>
  </>
}
