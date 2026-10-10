import { ArrowUpRight, FileText, MagnifyingGlass, UploadSimple } from '@phosphor-icons/react'
import { lazy, Suspense, useState } from 'react'
import { useWorkspace } from '../context'
import { dateLabel } from '../data'
import { liveEnabled } from '../lib/live'
import { Badge, Button, Empty } from './ui'
const LiveLibrary = lazy(() => import('../features/library/LiveLibrary').then(module => ({ default: module.LiveLibrary })))
const EvidencePage = lazy(() => import('../features/evidence/EvidencePage').then(module => ({ default: module.EvidencePage })))

export function Evidence() {
  const { workspace, line, market, requirements, openSource, openImport } = useWorkspace()
  const [query, setQuery] = useState(''), [family, setFamily] = useState('all')
  const [live, setLive] = useState(false)
  const linkedIds = new Set(requirements.flatMap(r => r.sourceIds))
  const inScope = workspace.sources.filter(s => linkedIds.has(s.id) || (s.line === line || s.line === 'All') && (s.market === market || s.market === 'All'))
  const families = [...new Set(inScope.map(s => s.family))].sort()
  const filtered = inScope.filter(s => `${s.name} ${s.locator}`.toLowerCase().includes(query.toLowerCase()) && (family === 'all' || s.family === family))
  const domains = [...new Set(requirements.map(r => r.domain))]
  return <>
    {liveEnabled && <div className="evidence-mode-controls"><Button variant={live ? 'secondary' : 'primary'} aria-pressed={!live} onClick={() => setLive(false)}>Demo sources</Button><Button variant={live ? 'primary' : 'secondary'} aria-pressed={live} onClick={() => setLive(true)}>Browse backend evidence</Button></div>}
    {live ? <section className="live-evidence"><p className="data-note">This browser queries the backend through /api. Its search filters are separate from the local demo programme; results are not added to your demo portfolio.</p><Suspense fallback={<p role="status">Loading evidence browser...</p>}><div className="flex flex-col gap-10"><LiveLibrary /><EvidencePage /></div></Suspense></section> : <>
    <div className="page-heading"><div><p className="eyebrow">EVIDENCE LIBRARY</p><h1>Every claim has a source.</h1><p>Keep the original context close to the decisions it supports.</p></div><Button onClick={openImport}><UploadSimple size={18} /> Add document</Button></div>
    <div className="notice"><FileText size={21} /><p>The built-in sources are illustrative. Added documents stay in this browser; their metadata is saved and text files can be previewed. Automated parsing and live ingestion are not connected.</p></div>
    <section className="filter-bar evidence-filters"><div className="search-field"><label htmlFor="source-search">Search evidence</label><div className="input-icon"><MagnifyingGlass size={18} /><input id="source-search" type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search a document or locator" /></div></div><div className="field"><label htmlFor="family-filter">Input family</label><select id="family-filter" value={family} onChange={e => setFamily(e.target.value)}><option value="all">All input families</option>{families.map(f => <option key={f}>{f}</option>)}</select></div></section>
    <div className="table-toolbar"><p>{filtered.length} sources in scope</p></div>
    {filtered.length ? <div className="source-grid">{filtered.map(s => <button className="source-card" key={s.id} onClick={() => openSource(s)}><div className="source-card-top"><span className="file-icon"><FileText size={25} /></span><Badge tone={s.uploaded ? 'warning' : s.level === 'Verified' ? 'success' : s.level === 'Unverified' ? 'warning' : 'neutral'}>{s.uploaded ? 'Not parsed' : `Demo ${s.level.toLowerCase()}`}</Badge></div><p className="eyebrow">{s.family.toUpperCase()}</p><h2>{s.name}<ArrowUpRight size={17} /></h2><p>{s.locator}</p><div className="source-card-footer"><span>{requirements.filter(r => r.sourceIds.includes(s.id)).length} linked requirements</span><time dateTime={s.addedAt}>{dateLabel(s.addedAt)}</time></div></button>)}</div> : <Empty title="No sources match this search">Try another document name or input family.</Empty>}
    <section className="coverage-section"><div className="section-heading"><div><h2>See where the evidence is thin.</h2><p>Linked source counts by domain and input family. Empty cells show coverage gaps.</p></div></div><div className="table-scroll" role="region" aria-label="Evidence coverage" tabIndex={0}><table className="coverage-table"><thead><tr><th scope="col">Domain</th>{['Customer feedback', 'Customer study', 'Product catalog', 'Competitor research', 'Market research'].map(f => <th key={f} scope="col">{f}</th>)}</tr></thead><tbody>{domains.map(d => <tr key={d}><th scope="row">{d}</th>{['Customer feedback', 'Customer study', 'Product catalog', 'Competitor research', 'Market research'].map(f => { const ids = new Set(requirements.filter(r => r.domain === d).flatMap(r => r.sourceIds)); const n = workspace.sources.filter(s => ids.has(s.id) && s.family === f).length; return <td key={f}><span className={n ? 'coverage-value' : 'coverage-zero'}>{n || 'No source'}</span></td> })}</tr>)}</tbody></table></div></section>
    </>}
  </>
}
