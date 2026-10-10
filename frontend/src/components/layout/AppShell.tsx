import { NavLink, Outlet } from 'react-router'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { cn } from '@/lib/utils'

const links = [
  { to: '/', label: 'Chat', end: true },
  { to: '/evidence', label: 'Evidence', end: false },
]

export function AppShell() {
  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-6 px-6">
          <div className="flex items-center gap-10">
            <span className="text-base font-bold">Requirement Evidence Engine</span>
            <nav aria-label="Main" className="flex h-16 items-stretch gap-6">
              {links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center border-b-2 text-sm tracking-wide text-foreground/80 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring',
                      isActive ? 'border-primary font-bold text-foreground' : 'border-transparent',
                    )
                  }
                >
                  {l.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <HealthBadge />
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-6 py-8">
        <Outlet />
      </main>
    </div>
  )
}
