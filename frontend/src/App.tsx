import { lazy, Suspense, useEffect, useState } from 'react'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { AuthGate, signOut } from '@/features/auth/AuthGate'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'

const LiveResearch = lazy(() => import('@/features/research/LiveResearch').then((m) => ({ default: m.LiveResearch })))
const EvidencePage = lazy(() => import('@/features/evidence/EvidencePage').then((m) => ({ default: m.EvidencePage })))
const LiveLibrary = lazy(() => import('@/features/library/LiveLibrary').then((m) => ({ default: m.LiveLibrary })))

const PAGES = [
  { id: 'research', label: 'Research', View: LiveResearch },
  { id: 'evidence', label: 'Evidence', View: EvidencePage },
  { id: 'sources', label: 'Sources', View: LiveLibrary },
] as const
type PageId = (typeof PAGES)[number]['id']

const fromHash = (): PageId => PAGES.find((p) => `#${p.id}` === window.location.hash)?.id ?? 'research'

function Shell() {
  const { user } = useAuth()
  const [page, setPage] = useState<PageId>(fromHash)
  const current = PAGES.find((p) => p.id === page) ?? PAGES[0]

  useEffect(() => {
    const onHash = () => setPage(fromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => { document.title = `${current.label} | BMW Product Intelligence` }, [current.label])

  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:p-3">Skip to main content</a>
      <header className="border-b border-border">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:gap-6 sm:px-6">
          <span className="font-bold tracking-wide">BMW<span className="hidden font-light sm:inline"> Product Intelligence</span></span>
          <nav aria-label="Main" className="flex h-full flex-1 gap-4 sm:gap-6">
            {PAGES.map((p) => (
              <a key={p.id} href={`#${p.id}`} aria-current={p.id === page ? 'page' : undefined}
                className={cn('flex h-full items-center border-b-2 text-sm focus-visible:outline-2 focus-visible:outline-ring',
                  p.id === page ? 'border-primary font-bold' : 'border-transparent text-muted-foreground hover:text-foreground')}>
                {p.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            {user && <span className="hidden sm:inline">{user.display_name}</span>}
            <Button variant="outline" onClick={signOut}>Sign out</Button>
          </div>
        </div>
      </header>
      <main id="main-content" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6 sm:py-10 outline-none">
        <Suspense fallback={<Skeleton className="h-48 w-full" aria-label="Loading" />}>
          <current.View />
        </Suspense>
      </main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl justify-end px-6 py-4"><HealthBadge /></div>
      </footer>
    </div>
  )
}

export function App() {
  return <AuthGate><Shell /></AuthGate>
}
