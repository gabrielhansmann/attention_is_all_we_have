import { lazy, Suspense, useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import { NAV, Sidebar, type PageId } from '@/components/layout/Sidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { AuthGate } from '@/features/auth/AuthGate'
import { ChatProvider } from '@/features/research/chat-store'

const LiveResearch = lazy(() => import('@/features/research/LiveResearch').then((m) => ({ default: m.LiveResearch })))
const ModelsPage = lazy(() => import('@/features/models/ModelsPage').then((m) => ({ default: m.ModelsPage })))
const EvidencePage = lazy(() => import('@/features/evidence/EvidencePage').then((m) => ({ default: m.EvidencePage })))
const LiveLibrary = lazy(() => import('@/features/library/LiveLibrary').then((m) => ({ default: m.LiveLibrary })))
const MarketImpact = lazy(() => import('@/features/market-impact/MarketImpact').then((m) => ({ default: m.MarketImpact })))

const RequirementsPage = lazy(() => import('@/features/requirements/RequirementsPage').then((m) => ({ default: m.RequirementsPage })))
const TrackingPage = lazy(() => import('@/features/requirements/TrackingPage').then((m) => ({ default: m.TrackingPage })))
const DossiersPage = lazy(() => import('@/features/requirements/DossiersPage').then((m) => ({ default: m.DossiersPage })))

const VIEWS: Record<PageId, React.ComponentType> = {
  models: ModelsPage,
  research: LiveResearch, requirements: RequirementsPage, tracking: TrackingPage, dossiers: DossiersPage,
  evidence: EvidencePage, sources: LiveLibrary, 'market-impact': MarketImpact,
}

// A hash may carry a query (`#requirements?tab=priorities`); only the part before it names the page.
const fromHash = (): PageId => NAV.find((p) => p.id === window.location.hash.slice(1).split('?')[0])?.id ?? 'research'

function Shell() {
  const [page, setPage] = useState<PageId>(fromHash)
  const [menu, setMenu] = useState(false)
  const label = NAV.find((p) => p.id === page)!.label
  const View = VIEWS[page]

  useEffect(() => {
    const onHash = () => setPage(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => { document.title = `${label} | BMW Product Intelligence` }, [label])

  const navigate = (p: PageId) => { window.location.hash = p; setPage(p) }

  return (
    <ChatProvider>
      <div className="flex h-dvh bg-background">
        <a href="#main-content" className="sr-only focus:not-sr-only focus:p-3">Skip to main content</a>
        <aside className="hidden w-72 shrink-0 border-r border-sidebar-border md:block"><Sidebar page={page} onNavigate={navigate} /></aside>
        <Sheet open={menu} onOpenChange={setMenu}>
          <SheetContent side="left" className="w-[19rem] max-w-[85vw] gap-0 p-0" showCloseButton={false}>
            <SheetTitle className="sr-only">Menu</SheetTitle>
            <SheetDescription className="sr-only">Navigation and chat history</SheetDescription>
            <Sidebar page={page} onNavigate={navigate} onDone={() => setMenu(false)} />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-12 items-center gap-2 border-b border-border px-3 md:hidden">
            <Button variant="ghost" size="icon" aria-label="Open menu" onClick={() => setMenu(true)}><Menu /></Button>
            <span className="text-sm font-semibold">{label}</span>
          </div>
          <main id="main-content" tabIndex={-1} className="flex min-h-0 flex-1 flex-col outline-none">
            <Suspense fallback={<div className="p-8"><Skeleton className="h-48 w-full rounded-2xl" aria-label="Loading" /></div>}>
              <View />
            </Suspense>
          </main>
        </div>
      </div>
    </ChatProvider>
  )
}

export function App() {
  return <AuthGate><Shell /></AuthGate>
}
