import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, ArrowUpRight, ChartBar, FileText, House, List, MagnifyingGlass, WarningCircle } from '@phosphor-icons/react'
import type { Page } from './data'
import type { StoredRequirement, WorkspaceConfig, WorkspaceSnapshot } from './types/api'
import { WorkspaceContext } from './context'
import { Badge, Button, Dialog } from './components/ui'
import { Overview } from './components/Overview'
import { Requirements } from './components/Requirements'
import { Reports } from './components/Reports'
import { RequirementDialog } from './components/WorkspaceDialogs'
import { AuthGate } from './features/auth/AuthGate'
import { api, ApiError } from './lib/api'
import { markRequired, useAuth } from './lib/auth'

const navigation: { id: Page; label: string; icon: typeof House }[] = [
  { id: 'overview', label: 'Overview', icon: House }, { id: 'requirements', label: 'Requirements', icon: List },
  { id: 'research', label: 'Research', icon: MagnifyingGlass }, { id: 'evidence', label: 'Evidence library', icon: FileText }, { id: 'reports', label: 'Reports', icon: ChartBar },
]
const currentPage = (): Page => navigation.find(n => `#${n.id}` === window.location.hash)?.id || 'overview'
const Research = lazy(() => import('./components/Research').then(module => ({ default: module.Research })))
const Evidence = lazy(() => import('./components/Evidence').then(module => ({ default: module.Evidence })))
type Loaded = { key: string; config: WorkspaceConfig; data: WorkspaceSnapshot } | { key: string; error: string }

function WorkspaceApp() {
  const { user } = useAuth()
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [line, setLine] = useState(''), [market, setMarket] = useState(''), [page, setPage] = useState<Page>(currentPage)
  const [revision, setRevision] = useState(0)
  const [mobileOpen, setMobileOpen] = useState(false), [toast, setToast] = useState('')
  const [requirementId, setRequirementId] = useState<string | null>(null)
  const key = JSON.stringify([line, market])
  const selection = useRef(key)
  const ready = loaded?.key === key && 'data' in loaded ? loaded : null
  const config = loaded && 'data' in loaded ? loaded.config : undefined
  const lineLabel = useCallback((value: string) => value === 'ALL' || !value ? 'All vehicle lines' : config?.lines.find(l => l.key === value)?.label ?? value, [config])
  const marketLabel = useCallback((value: string) => value === 'ALL' || !value ? 'All markets' : config?.markets.find(m => m.key === value)?.label ?? value, [config])
  const notify = useCallback((message: string) => setToast(message), [])
  const navigate = useCallback((next: Page) => { window.location.hash = next; setPage(next); setMobileOpen(false); setRequirementId(null); window.scrollTo({ top: 0, behavior: 'instant' }) }, [])
  const refresh = useCallback(async () => {
    const [nextConfig, nextData] = await Promise.all([api.workspaceConfig(), api.workspace(line, market)])
    if (selection.current === key) setLoaded({ key, config: nextConfig, data: nextData })
  }, [line, market, key])

  useEffect(() => {
    const ctrl = new AbortController()
    Promise.all([api.workspaceConfig(ctrl.signal), api.workspace(line, market, ctrl.signal)])
      .then(([nextConfig, nextData]) => { if (!ctrl.signal.aborted) setLoaded({ key, config: nextConfig, data: nextData }) })
      .catch(e => { if (!ctrl.signal.aborted) setLoaded({ key, error: e instanceof ApiError ? e.message : 'Workspace data could not be loaded.' }) })
    return () => ctrl.abort()
  }, [line, market, key, revision, page])
  useEffect(() => {
    const onHashChange = () => { setPage(currentPage()); setMobileOpen(false); setRequirementId(null) }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  useEffect(() => { document.title = `${navigation.find(n => n.id === page)?.label} | BMW Product Intelligence` }, [page])
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer) }, [toast])

  async function signOut() {
    try { await api.logout() } finally { markRequired() }
  }
  function scopeChanged(nextLine: string, nextMarket: string) {
    selection.current = JSON.stringify([nextLine, nextMarket])
    setLine(nextLine); setMarket(nextMarket); setRequirementId(null)
  }
  const waiting = ready?.data.requirements.filter(r => r.status === 'pm_review' || r.status === 'challenged').length ?? 0
  const selectedRequirement = ready?.data.requirements.find(r => r.id === requirementId)
  const sidebar = <>
    <a href="#overview" className="brand" aria-label="BMW Product Intelligence home" onClick={() => navigate('overview')}><span className="brand-wordmark">BMW</span><span>PRODUCT<br /><strong>INTELLIGENCE</strong></span></a>
    <div className="sidebar-programme"><span className="eyebrow">YOUR SCOPE</span><strong>{lineLabel(line)}</strong><span>{marketLabel(market)}</span></div>
    <nav aria-label="Workspace navigation">{navigation.map(n => <a href={`#${n.id}`} key={n.id} aria-label={n.label} aria-current={page === n.id ? 'page' : undefined} className={`nav-item ${page === n.id ? 'nav-active' : ''}`} onClick={() => navigate(n.id)}><n.icon size={21} weight={page === n.id ? 'fill' : 'regular'} /><span>{n.label}</span>{n.id === 'requirements' && waiting > 0 && <span className="nav-count" aria-hidden="true">{waiting}</span>}</a>)}</nav>
    <div className="sidebar-bottom"><div className="data-marker"><Badge>Connected workspace</Badge><p>Database evidence and<br />stored research results.</p></div><div className="profile"><span className="avatar">{user?.display_name.split(' ').map(n => n[0]).slice(0, 2).join('')}</span><div><strong>{user?.display_name}</strong><span>{user?.role}</span></div></div></div>
  </>
  const body = ready ? <WorkspaceContext.Provider value={{ data: ready.data, config: ready.config, line, market, lineLabel, marketLabel, navigate, notify, refresh, openRequirement: (r: StoredRequirement) => setRequirementId(r.id) }}>
    <Suspense fallback={<p role="status">Loading view...</p>}>{page === 'overview' ? <Overview /> : page === 'requirements' ? <Requirements key={key} /> : page === 'research' ? <Research /> : page === 'evidence' ? <Evidence /> : <Reports />}</Suspense>
    {selectedRequirement && <RequirementDialog key={selectedRequirement.id} requirement={selectedRequirement} close={() => setRequirementId(null)} />}
  </WorkspaceContext.Provider> : loaded?.key === key && 'error' in loaded ? <div className="notice" role="alert"><WarningCircle size={22} /><div><h1>Workspace unavailable</h1><p>{loaded.error}</p><Button variant="secondary" onClick={() => setRevision(r => r + 1)}>Try again</Button></div></div> : <section aria-live="polite" aria-busy="true"><h1>Loading workspace</h1><p>Reading the evidence store.</p></section>
  return <>
    <a className="skip-link" href="#main-content">Skip to main content</a>
    <div className="app-layout"><aside className="sidebar">{sidebar}</aside><div className="workspace-main"><header className="topbar"><div className="topbar-location"><Button variant="ghost" size="icon" className="mobile-menu-button" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><List size={24} /></Button><span>Product development</span><ArrowRight size={14} /><strong>{navigation.find(n => n.id === page)?.label}</strong></div><div className="scope-controls"><div><label htmlFor="vehicle-line">Vehicle line</label><select id="vehicle-line" value={line} disabled={!config} onChange={e => scopeChanged(e.target.value, market)}><option value="">All vehicle lines</option>{config?.lines.map(l => <option key={l.key} value={l.key}>{l.label} / {l.key}</option>)}</select></div><div><label htmlFor="market">Market</label><select id="market" value={market} disabled={!config} onChange={e => scopeChanged(line, e.target.value)}><option value="">All markets</option>{config?.markets.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}</select></div></div></header>
      <main id="main-content" className="main-content" tabIndex={-1}>
        <div className="session-controls no-print"><span>{user ? `Signed in as ${user.display_name}` : 'Signed in'}</span><Button variant="secondary" size="small" onClick={() => setRevision(r => r + 1)}>Refresh data</Button><Button variant="ghost" size="small" onClick={() => { void signOut().catch(() => undefined) }}>Sign out</Button></div>
        {body}
        <footer className="workspace-footer"><span>BMW Product Intelligence</span><span>Evidence informs. You decide.</span><span>Connected workspace <ArrowUpRight size={12} /></span></footer>
      </main></div></div>
    <Dialog open={mobileOpen} onOpenChange={setMobileOpen} title="Workspace navigation" description="Choose a workspace view."><div className="mobile-nav">{sidebar}</div></Dialog>
    {toast && <div className="toast" role="status">{toast}</div>}
  </>
}

export function App() {
  return <AuthGate><WorkspaceApp /></AuthGate>
}
