import { ArrowRight, ArrowUpRight, ChartLineUp, CheckCircle, Files, MagnifyingGlass, SlidersHorizontal, WarningCircle } from '@phosphor-icons/react'
import { useWorkspace } from '../context'
import { composite, dateLabel, formatNumber, lineNames, marketNames, priorityNames, scopeKey, tier } from '../data'
import type { Metric } from '../data'
import { Badge, Button, Empty } from './ui'

function Sparkline({ metric }: { metric: Metric }) {
  const all = [...metric.trend, metric.target]
  const min = Math.min(...all) * 0.9, max = Math.max(...all) * 1.06
  const y = (n: number) => 54 - (n - min) / (max - min) * 42
  const points = metric.trend.map((n, i) => `${12 + i * 62},${y(n)}`).join(' ')
  return <svg viewBox="0 0 216 64" className="sparkline" role="img" aria-label={`${metric.label}: illustrative history ${metric.trend.join(', ')}, target ${metric.target}`}>
    <line x1="12" y1="57" x2="204" y2="57" className="chart-grid" />
    <polyline points={points} className="chart-line" />
    <line x1="136" y1={y(metric.baseline)} x2="198" y2={y(metric.target)} className="chart-target" />
    {metric.trend.map((n, i) => <circle key={i} cx={12 + i * 62} cy={y(n)} r="3" className="chart-point" />)}
    <circle cx="198" cy={y(metric.target)} r="4" className="chart-target-point" />
  </svg>
}

export function Overview() {
  const { workspace, line, market, requirements, metrics, audits, navigate, openSource, openRequirement, openTarget, openWeights, mutate } = useWorkspace()
  const review = requirements.filter(r => r.status === 'pm_review' || r.status === 'challenged')
  const must = requirements.filter(r => tier(composite(r, workspace.weights)) === 'Must-have' && r.status !== 'rejected')
  const sourceIds = new Set(requirements.flatMap(r => r.sourceIds))
  const thin = requirements.filter(r => r.confidence < 60 || r.sourceIds.length < 2)
  const activeRuns = workspace.runs.filter(r => r.line === line && r.market === market && r.status === 'active')
  const statItems = [
    { label: 'Requirements in scope', value: requirements.length, detail: `${requirements.filter(r => r.status === 'tracked').length} tracked by the programme`, icon: Files, page: 'requirements' as const },
    { label: 'Must-have priorities', value: must.length, detail: 'Based on your current weights', icon: ChartLineUp, page: 'requirements' as const },
    { label: 'Decisions waiting', value: review.length + activeRuns.length, detail: 'Your review moves things forward', icon: CheckCircle, page: 'requirements' as const },
    { label: 'Sources supporting decisions', value: sourceIds.size, detail: thin.length ? `${thin.length} requirement${thin.length === 1 ? ' needs' : 's need'} more evidence` : 'Citations attached to every requirement', icon: MagnifyingGlass, page: 'evidence' as const },
  ]
  return <>
    <section className="hero-band">
      <div><p className="eyebrow">{lineNames[line].toUpperCase()} SUCCESSOR PROGRAMME</p><h1>Build what comes next.</h1><p className="hero-description">Turn customer evidence into confident product decisions.</p>
        <div className="hero-scope"><span>{line} baseline</span><span>{marketNames[market]}</span><span>Sample programme</span></div></div>
      <Button onClick={() => navigate('research')}>Start research <ArrowUpRight size={19} /></Button>
    </section>
    <div className="stat-grid">{statItems.map(s => <button className="stat-cell" key={s.label} onClick={() => navigate(s.page)}><span className="stat-label">{s.label}<s.icon size={19} /></span><strong>{s.value.toString().padStart(2, '0')}</strong><span className="stat-detail">{s.detail}</span></button>)}</div>
    <div className="overview-grid">
      <section className="baseline-panel">
        <div className="section-heading"><div><h2>A clear direction for the successor.</h2><p>Your baseline, the segment, and the targets you want to reach.</p></div><Badge>Illustrative metrics</Badge></div>
        <div className="table-scroll" role="region" aria-label="Product baseline and targets" tabIndex={0}><table className="baseline-table"><thead><tr><th scope="col">Product aspect</th><th scope="col">Current</th><th scope="col">Segment</th><th scope="col">Your target</th><th scope="col">Priority</th></tr></thead>
          <tbody>{metrics.map(metric => <tr key={metric.id}><td><button className="table-title" onClick={() => openSource(workspace.sources.find(s => s.id === metric.sourceId)!)}>{metric.label}<ArrowUpRight size={13} /></button><span className="cell-caption">{metric.unit} · {metric.lower ? 'Lower is better' : 'Higher is better'}</span></td><td>{formatNumber(metric.baseline)}</td><td className="muted">{formatNumber(metric.competition)}</td><td><button className="target-value" onClick={() => openTarget(metric)} aria-label={`Edit ${metric.label} target`}>{formatNumber(metric.target)}<ArrowUpRight size={14} /></button></td><td><select className="priority-select" aria-label={`${metric.label} priority`} value={metric.priority} onChange={e => { const value = Number(e.target.value); mutate(`${metric.label} priority changed`, `Priority set to ${priorityNames[value - 1]}.`, s => ({ ...s, metrics: { ...s.metrics, [scopeKey(line, market)]: metrics.map(m => m.id === metric.id ? { ...m, priority: value } : m) } })) }}>{priorityNames.map((name, i) => <option key={name} value={i + 1}>{name}</option>)}</select></td></tr>)}</tbody></table></div>
        <div className="panel-footnote"><span>Same scope. Same measurement standard. Sources on every aspect.</span><Button variant="ghost" size="small" onClick={openWeights}><SlidersHorizontal size={16} /> Set scoring weights</Button></div>
      </section>
      <aside className="decision-panel"><div className="section-heading"><div><p className="eyebrow">PM INBOX</p><h2>Your next decisions.</h2></div><Badge tone="blue">{review.length + activeRuns.length}</Badge></div>
        {review.length === 0 && activeRuns.length === 0 ? <Empty title="You're up to date">There are no decisions waiting in this scope.</Empty> : <div className="decision-list">{review.slice(0, 3).map(r => <button key={r.id} className="decision-item" onClick={() => openRequirement(r)}><span className="decision-icon">{r.status === 'challenged' ? <WarningCircle size={20} /> : <CheckCircle size={20} />}</span><span><span className="cell-caption">{r.id} · {r.status === 'challenged' ? 'Evidence challenged' : 'Ready for review'}</span><strong>{r.title}</strong><span className="cell-caption">{r.sourceIds.length} sources · {r.confidence}% confidence</span></span><ArrowRight size={16} /></button>)}{activeRuns.slice(0, 1).map(r => <button key={r.id} className="decision-item" onClick={() => navigate('research')}><span className="decision-icon"><MagnifyingGlass size={20} /></span><span><span className="cell-caption">Research awaiting review</span><strong>{r.query}</strong></span><ArrowRight size={16} /></button>)}</div>}
        <Button variant="ghost" className="all-decisions" onClick={() => navigate('requirements')}>View all requirements <ArrowRight size={16} /></Button>
      </aside>
    </div>
    <section className="trend-section"><div className="section-heading"><div><h2>Progress has a direction.</h2><p>Illustrative history alongside the targets you set. Dashed lines show your target.</p></div><Badge>2024-2026 + target</Badge></div>
      <div className="trend-grid">{metrics.map(m => <button className="trend-card" key={m.id} onClick={() => openTarget(m)}><span className="stat-label">{m.label}<ArrowUpRight size={16} /></span><div className="trend-value"><strong>{formatNumber(m.target)}</strong><span>{m.unit}</span><Badge tone="blue">Target</Badge></div><Sparkline metric={m} /><div className="chart-labels"><span>2024</span><span>2025</span><span>Baseline</span><span>Target</span></div></button>)}</div>
    </section>
    <section className="activity-section"><div className="section-heading"><div><h2>A decision you can trace.</h2><p>Every change keeps its context, author, and reason.</p></div><Button variant="ghost" size="small" onClick={() => navigate('reports')}>Programme report <ArrowRight size={16} /></Button></div>
      {audits.length ? <div className="activity-list">{audits.slice(0, 4).map(a => <div className="activity-row" key={a.id}><span className="activity-mark"><CheckCircle size={19} /></span><div><strong>{a.title}</strong><p>{a.detail}</p></div><div className="activity-meta"><span>{a.actor}</span><time dateTime={a.time}>{dateLabel(a.time)}</time></div></div>)}</div> : <Empty title="Start your decision trail">Update a priority, set a target, or review a requirement to record the first change.</Empty>}
    </section>
  </>
}
