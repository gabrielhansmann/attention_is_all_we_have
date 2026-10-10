import { useCallback, useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, ArrowUpRight, ChartBar, CheckCircle, FileText, GearSix, House, List, MagnifyingGlass, WarningCircle, X } from '@phosphor-icons/react'
import { createWorkspace, lineNames, marketNames, scopeKey, storageKey, uid } from './data'
import type { Line, Market, Metric, Page, Requirement, Source, Workspace } from './data'
import { WorkspaceContext } from './context'
import { Badge, Button, Dialog } from './components/ui'
import { Overview } from './components/Overview'
import { Requirements } from './components/Requirements'
import { Research } from './components/Research'
import { Evidence } from './components/Evidence'
import { Reports } from './components/Reports'
import { ImportDialog, RequirementDialog, SettingsDialog, SourceDialog, TargetDialog, WeightsDialog } from './components/WorkspaceDialogs'

const navigation: { id: Page; label: string; icon: typeof House }[] = [
  { id: 'overview', label: 'Overview', icon: House }, { id: 'requirements', label: 'Requirements', icon: List },
  { id: 'research', label: 'Research', icon: MagnifyingGlass }, { id: 'evidence', label: 'Evidence library', icon: FileText }, { id: 'reports', label: 'Reports', icon: ChartBar },
]
const currentPage = (): Page => navigation.find(n => `#${n.id}` === window.location.hash)?.id || 'overview'
function loadWorkspace(): { workspace: Workspace; error: string } {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return { workspace: createWorkspace(), error: '' }
    const saved = JSON.parse(raw) as Workspace
    if (saved.version !== 1 || !Array.isArray(saved.requirements) || !Array.isArray(saved.sources) || !Array.isArray(saved.runs) || !Array.isArray(saved.audits) || !saved.metrics || !saved.weights) throw new Error('Unsupported saved workspace')
    return { workspace: saved, error: '' }
  } catch { return { workspace: createWorkspace(), error: 'Saved data could not be loaded. A fresh demo is shown; export your work before leaving if browser storage is unavailable.' } }
}

export function App() {
  const [loaded] = useState(loadWorkspace)
  const [workspace, setWorkspace] = useState(loaded.workspace), [storageError, setStorageError] = useState(loaded.error)
  const [line, setLine] = useState<Line>('G60'), [market, setMarket] = useState<Market>('EU'), [page, setPage] = useState<Page>(currentPage)
  const [mobileOpen, setMobileOpen] = useState(false), [toast, setToast] = useState('')
  const [source, setSource] = useState<Source | null>(null), [requirementId, setRequirementId] = useState<string | null>(null), [target, setTarget] = useState<Metric | null>(null)
  const [modal, setModal] = useState<'import' | 'weights' | 'settings' | 'reset' | null>(null)
  const requirements = workspace.requirements.filter(r => r.line === line && r.market === market)
  const metrics = workspace.metrics[scopeKey(line, market)] || []
  const audits = workspace.audits.filter(a => a.line === line && a.market === market)
  const selectedRequirement = workspace.requirements.find(r => r.id === requirementId)
  const notify = useCallback((message: string) => setToast(message), [])
  const navigate = useCallback((next: Page) => { window.location.hash = next; setPage(next); setMobileOpen(false); window.scrollTo({ top: 0, behavior: 'instant' }) }, [])
  const mutate = useCallback((title: string, detail: string, update: (state: Workspace) => Workspace, actor = 'You') => {
    const event = { id: uid(), title, detail, actor, time: new Date().toISOString(), line, market }
    setWorkspace(prev => { const next = update(prev); return { ...next, audits: [event, ...next.audits] } })
  }, [line, market])
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify(workspace)) }
    catch { setStorageError('Browser storage is full or unavailable. Your current session still works. Download a workspace backup to keep your changes.') }
  }, [workspace])
  useEffect(() => {
    const onHashChange = () => { if (navigation.some(n => `#${n.id}` === window.location.hash)) setPage(currentPage()); setMobileOpen(false) }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  useEffect(() => { document.title = `${navigation.find(n => n.id === page)?.label} | BMW Product Intelligence` }, [page])
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer) }, [toast])
  const waiting = requirements.filter(r => r.status === 'pm_review' || r.status === 'challenged').length
  const sidebar = <>
    <a href="#overview" className="brand" aria-label="BMW Product Intelligence home" onClick={() => navigate('overview')}><span className="brand-wordmark">BMW</span><span>PRODUCT<br /><strong>INTELLIGENCE</strong></span></a>
    <div className="sidebar-programme"><span className="eyebrow">YOUR PROGRAMME</span><strong>{lineNames[line]} successor</strong><span>{line} · {marketNames[market]}</span></div>
    <nav aria-label="Workspace navigation">{navigation.map(n => <a href={`#${n.id}`} key={n.id} aria-label={n.label} aria-current={page === n.id ? 'page' : undefined} className={`nav-item ${page === n.id ? 'nav-active' : ''}`} onClick={() => navigate(n.id)}><n.icon size={21} weight={page === n.id ? 'fill' : 'regular'} /><span>{n.label}</span>{n.id === 'requirements' && waiting > 0 && <span className="nav-count" aria-hidden="true">{waiting}</span>}</a>)}</nav>
    <div className="sidebar-bottom"><div className="demo-marker"><Badge>Demo workspace</Badge><p>Illustrative data.<br />Your decisions, saved locally.</p></div><button className="nav-item" onClick={() => { setModal('settings'); setMobileOpen(false) }}><GearSix size={21} /><span>Workspace settings</span></button><div className="profile"><span className="avatar">PM</span><div><strong>Product manager</strong><span>Successor programme</span></div></div></div>
  </>
  return <WorkspaceContext.Provider value={{ workspace, line, market, requirements, metrics, audits, navigate, notify, mutate, openSource: setSource, openRequirement: (r: Requirement) => setRequirementId(r.id), openTarget: setTarget, openImport: () => setModal('import'), openWeights: () => setModal('weights') }}>
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <div className="app-layout"><aside className="sidebar">{sidebar}</aside><div className="workspace-main"><header className="topbar"><div className="topbar-location"><Button variant="ghost" size="icon" className="mobile-menu-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><List size={24} /></Button><span>Product development</span><ArrowRight size={14} /><strong>{navigation.find(n => n.id === page)?.label}</strong></div><div className="scope-controls"><div><label htmlFor="vehicle-line">Vehicle line</label><select id="vehicle-line" value={line} onChange={e => { setLine(e.target.value as Line); setTarget(null); setRequirementId(null); setSource(null) }}>{(Object.keys(lineNames) as Line[]).map(l => <option key={l} value={l}>{lineNames[l]} / {l}</option>)}</select></div><div><label htmlFor="market">Market</label><select id="market" value={market} onChange={e => { setMarket(e.target.value as Market); setTarget(null); setRequirementId(null); setSource(null) }}>{(Object.keys(marketNames) as Market[]).map(m => <option key={m} value={m}>{marketNames[m]}</option>)}</select></div></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>{storageError && <div className="notice storage-notice" role="alert"><WarningCircle size={20} /><p>{storageError}</p><Button variant="ghost" size="small" onClick={() => setModal('settings')}>Export backup</Button></div>}
        {page === 'overview' ? <Overview /> : page === 'requirements' ? <Requirements key={scopeKey(line, market)} /> : page === 'research' ? <Research key={scopeKey(line, market)} /> : page === 'evidence' ? <Evidence key={scopeKey(line, market)} /> : <Reports />}
        <footer className="workspace-footer"><span>BMW Product Intelligence</span><span>Evidence informs. You decide.</span><button onClick={() => setModal('settings')}>Local demo workspace <ArrowUpRight size={12} /></button></footer>
      </main></div></div>
    <Dialog open={mobileOpen} onOpenChange={setMobileOpen} title="Workspace navigation" description="Choose a workspace view."><div className="mobile-navigation">{sidebar}</div></Dialog>
    <SourceDialog source={source} close={() => setSource(null)} />
    {selectedRequirement && <RequirementDialog key={selectedRequirement.id} requirement={selectedRequirement} close={() => setRequirementId(null)} />}
    {target && <TargetDialog key={target.id} metric={target} close={() => setTarget(null)} />}
    {modal === 'import' && <ImportDialog close={() => setModal(null)} />}
    {modal === 'weights' && <WeightsDialog close={() => setModal(null)} />}
    {modal === 'settings' && <SettingsDialog close={() => setModal(null)} reset={() => setModal('reset')} />}
    <Dialog open={modal === 'reset'} onOpenChange={open => { if (!open) setModal(null) }} title="Reset your demo workspace?" description="This clears locally saved edits, added documents, research runs, and decision history."><div className="dialog-body"><p>Your workspace can be exported from settings before resetting.</p><div className="dialog-actions"><Button variant="secondary" onClick={() => setModal('settings')}><ArrowLeft size={16} /> Keep my workspace</Button><Button variant="danger" onClick={() => { setWorkspace(createWorkspace()); setModal(null); setRequirementId(null); setSource(null); setTarget(null); setStorageError(''); notify('Demo workspace reset.') }}>Reset workspace</Button></div></div></Dialog>
    {toast && <div className="toast no-print" role="status"><CheckCircle size={20} /><span>{toast}</span><Button variant="ghost" size="icon" aria-label="Dismiss notification" onClick={() => setToast('')}><X size={18} /></Button></div>}
  </WorkspaceContext.Provider>
}
