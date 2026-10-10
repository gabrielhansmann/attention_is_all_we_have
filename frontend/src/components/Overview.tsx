import { ArrowUpRight, CheckCircle, Files, MagnifyingGlass, ChartBar } from '@phosphor-icons/react'
import { useWorkspace } from '../context'
import { formatNumber } from '../data'
import { Badge, Button, Empty } from './ui'
import { AcceptedResults, CatalogTable, DecisionHistory, SalesTable, StudyTable } from './WorkspaceData'

export function Overview() {
  const { data, line, market, lineLabel, marketLabel, navigate, openRequirement } = useWorkspace()
  const review = data.requirements.filter(r => r.status === 'pm_review' || r.status === 'challenged')
  const stats = [
    { label: 'Stored requirements', value: data.requirements.length, detail: `${review.length} waiting for review`, icon: Files, page: 'requirements' as const },
    { label: 'Customer comments', value: data.counts.feedback, detail: 'Loaded feedback in this scope', icon: MagnifyingGlass, page: 'evidence' as const },
    { label: 'Study cells', value: data.counts.study_cells, detail: 'Recorded study values', icon: ChartBar, page: 'evidence' as const },
    { label: 'Agent reviews waiting', value: data.counts.pending_steps, detail: 'Stored steps awaiting your decision', icon: CheckCircle, page: 'research' as const },
  ]
  return <>
    <section className="hero-band"><div><p className="eyebrow">PRODUCT DECISION WORKSPACE</p><h1>Build what comes next.</h1><p className="hero-description">Turn customer evidence into confident product decisions.</p><div className="hero-scope"><span>{lineLabel(line)}</span><span>{marketLabel(market)}</span></div></div><Button onClick={() => navigate('research')}>Start research <ArrowUpRight size={19} /></Button></section>
    <div className="stat-grid">{stats.map(s => <button className="stat-cell" key={s.label} onClick={() => navigate(s.page)}><span className="stat-label">{s.label}<s.icon size={19} /></span><strong>{formatNumber(s.value)}</strong><span className="stat-detail">{s.detail}</span></button>)}</div>
    <section className="activity-section"><div className="section-heading"><div><h2>Your next decisions.</h2><p>Requirements and agent contributions waiting for review.</p></div><Badge tone="blue">{review.length + data.counts.pending_steps}</Badge></div>{review.length ? <div className="decision-list">{review.map(r => <button key={r.id} className="decision-item" onClick={() => openRequirement(r)}><span><strong>{r.title}</strong><span className="cell-caption">{r.code || r.id}</span></span><ArrowUpRight size={18} /></button>)}</div> : <Empty title="No requirements waiting for review">{data.counts.pending_steps ? 'Agent contributions are waiting in Research.' : 'Start research to collect and review evidence.'}</Empty>}{data.counts.pending_steps > 0 && <Button variant="secondary" onClick={() => navigate('research')}>Review agent contributions</Button>}</section>
    <section className="activity-section"><div className="section-heading"><div><h2>Recorded sales and forecasts.</h2><p>Years, volumes and forecast status come from the source rows.</p></div></div><SalesTable /></section>
    <section className="activity-section"><div className="section-heading"><div><h2>The equipment baseline.</h2><p>Extracted catalog entries with original page and equipment references.</p></div></div><CatalogTable /></section>
    <section className="activity-section"><div className="section-heading"><div><h2>Customer study evidence.</h2><p>Recorded answers in the selected scope.</p></div></div><StudyTable /></section>
    <section className="activity-section"><div className="section-heading"><div><h2>Accepted research.</h2><p>Cited agent contributions stored after PM review.</p></div></div><AcceptedResults /></section>
    <section className="activity-section"><div className="section-heading"><div><h2>A decision you can trace.</h2><p>Saved actions, authors and reasons.</p></div></div><DecisionHistory limit={8} /></section>
  </>
}
