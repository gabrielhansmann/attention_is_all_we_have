import { ArrowDown, ArrowUpRight, DownloadSimple, MagnifyingGlass, SlidersHorizontal } from '@phosphor-icons/react'
import { useState } from 'react'
import { useWorkspace } from '../context'
import { composite, downloadFile, portfolioCsv, statusNames, tier } from '../data'
import type { Status } from '../data'
import { Badge, Button, Empty } from './ui'

export function Requirements() {
  const { workspace, line, market, requirements, openRequirement, openWeights, notify } = useWorkspace()
  const [query, setQuery] = useState(''), [status, setStatus] = useState('all'), [domain, setDomain] = useState('all'), [sort, setSort] = useState('score')
  const [tierFilter, setTierFilter] = useState('all')
  const domains = [...new Set(requirements.map(r => r.domain))].sort()
  const filtered = requirements.filter(r => `${r.title} ${r.id} ${r.description}`.toLowerCase().includes(query.toLowerCase()) && (status === 'all' || r.status === status) && (domain === 'all' || r.domain === domain) && (tierFilter === 'all' || tier(composite(r, workspace.weights)) === tierFilter)).sort((a, b) => sort === 'score' ? composite(b, workspace.weights) - composite(a, workspace.weights) : sort === 'confidence' ? b.confidence - a.confidence : a.title.localeCompare(b.title))
  const exportCsv = () => { downloadFile(`requirements-${line}-${market}.csv`, portfolioCsv(filtered, workspace.weights, workspace.sources), 'text/csv;charset=utf-8'); notify('Filtered portfolio exported with citations.') }
  return <>
    <div className="page-heading"><div><p className="eyebrow">REQUIREMENT PORTFOLIO</p><h1>Evidence into action.</h1><p>Define the successor. Keep the reasoning behind every decision.</p></div><Button variant="secondary" onClick={exportCsv} disabled={!filtered.length}><DownloadSimple size={18} /> Export portfolio</Button></div>
    <div className="portfolio-summary"><span><strong>{requirements.length}</strong> requirements</span><span><strong>{requirements.filter(r => r.status === 'tracked').length}</strong> tracked</span><span><strong>{requirements.filter(r => r.status === 'pm_review').length}</strong> in review</span><Button variant="ghost" size="small" onClick={openWeights}><SlidersHorizontal size={18} /> Scoring weights</Button></div>
    <section aria-label="Filter requirements" className="filter-bar"><div className="search-field"><label htmlFor="requirement-search">Search requirements</label><div className="input-icon"><MagnifyingGlass size={18} /><input id="requirement-search" type="search" placeholder="Search a title or requirement ID" value={query} onChange={e => setQuery(e.target.value)} /></div></div>
      <div className="field"><label htmlFor="status-filter">Status</label><select id="status-filter" value={status} onChange={e => setStatus(e.target.value)}><option value="all">All statuses</option>{(Object.keys(statusNames) as Status[]).map(s => <option key={s} value={s}>{statusNames[s]}</option>)}</select></div>
      <div className="field"><label htmlFor="domain-filter">Domain</label><select id="domain-filter" value={domain} onChange={e => setDomain(e.target.value)}><option value="all">All domains</option>{domains.map(d => <option key={d}>{d}</option>)}</select></div>
      <div className="field"><label htmlFor="tier-filter">Tier</label><select id="tier-filter" value={tierFilter} onChange={e => setTierFilter(e.target.value)}><option value="all">All tiers</option>{['Must-have', 'Should-have', 'Watch-list'].map(t => <option key={t}>{t}</option>)}</select></div></section>
    <div className="table-toolbar"><p>{filtered.length} of {requirements.length} requirements</p><label>Sort by <select aria-label="Sort requirements" value={sort} onChange={e => setSort(e.target.value)}><option value="score">Priority score</option><option value="confidence">Confidence</option><option value="title">Title</option></select><ArrowDown size={15} /></label></div>
    {filtered.length ? <div className="table-scroll" role="region" aria-label="Requirement portfolio" tabIndex={0}><table className="requirement-table"><thead><tr><th scope="col">Requirement</th><th scope="col">Domain</th><th scope="col">Status</th><th scope="col">Priority</th><th scope="col">Confidence</th><th scope="col">Sources</th></tr></thead><tbody>{filtered.map(r => {
      const score = composite(r, workspace.weights), t = tier(score)
      return <tr key={r.id}><td><span className="cell-caption">{r.id}</span><button className="table-title" onClick={() => openRequirement(r)}>{r.title}<ArrowUpRight size={15} /></button><span className="cell-caption">{r.metric}</span></td><td>{r.domain}</td><td><Badge tone={r.status === 'tracked' ? 'success' : r.status === 'challenged' ? 'warning' : r.status === 'pm_review' ? 'blue' : 'neutral'}>{statusNames[r.status]}</Badge></td><td><div className="score-cell"><strong>{score.toFixed(2)}</strong><span className={t === 'Must-have' ? 'blue-text' : 'muted'}>{t}</span></div></td><td><div className="confidence-cell"><span>{r.confidence}%</span><div className="confidence-track"><span style={{ width: `${r.confidence}%` }} /></div>{r.confidence < 60 && <span className="cell-caption">Thin evidence</span>}</div></td><td><button className="source-count" onClick={() => openRequirement(r)} aria-label={`View ${r.sourceIds.length} sources for ${r.title}`}>{r.sourceIds.length}<ArrowUpRight size={13} /></button></td></tr>
    })}</tbody></table></div> : <Empty title="No requirements match these filters">Try another search, status, or domain.</Empty>}
    <p className="data-note">Priority and confidence are separate. A high score does not mean the evidence is complete. All programme values are sample data.</p>
  </>
}
