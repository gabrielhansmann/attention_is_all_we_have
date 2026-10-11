import { Car, ClipboardCheck, Database, Globe2, FileText, LogOut, MessageSquare, Plus, Radar, Search, type LucideIcon } from 'lucide-react'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { signOut } from '@/features/auth/AuthGate'
import { useChats } from '@/features/research/chat-store'
import { useAuth } from '@/lib/auth'
import { cn } from '@/lib/utils'
import type { Conversation } from '@/types/api'

export type PageId = 'models' | 'research' | 'requirements' | 'tracking' | 'dossiers' | 'evidence' | 'sources' | 'market-impact'

export const NAV: { id: PageId; label: string; Icon: LucideIcon }[] = [
  { id: 'models', label: 'Models', Icon: Car },
  { id: 'research', label: 'Research', Icon: MessageSquare },
  { id: 'requirements', label: 'Requirements', Icon: ClipboardCheck },
  { id: 'tracking', label: 'Tracking', Icon: Radar },
  { id: 'dossiers', label: 'Dossiers', Icon: FileText },
  { id: 'evidence', label: 'Evidence', Icon: Search },
  { id: 'sources', label: 'Sources', Icon: Database },
  { id: 'market-impact', label: 'Market impact', Icon: Globe2 },
]

const DAY = 86_400_000
function bucket(iso: string): string {
  const age = (Date.now() - new Date(iso).getTime()) / DAY
  if (age < 1) return 'Today'
  if (age < 2) return 'Yesterday'
  if (age < 8) return 'Previous 7 days'
  return 'Older'
}
const ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Older']

function group(list: Conversation[]) {
  const sorted = [...list].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  return ORDER.map((label) => ({ label, items: sorted.filter((c) => bucket(c.updated_at) === label) })).filter((g) => g.items.length)
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join('') || '?'

interface Props {
  page: string
  onNavigate: (page: PageId) => void
  onDone?: () => void
}

export function Sidebar({ page, onNavigate, onDone }: Props) {
  const { user } = useAuth()
  const { list, listLoading, listError, activeId, select } = useChats()

  const go = (p: PageId, id: string | null = null) => {
    select(id)
    onNavigate(p)
    onDone?.()
  }

  return (
    <div data-testid="sidebar" className="flex h-full flex-col gap-3 bg-sidebar p-3">
      <div className="flex items-center gap-2.5 px-2 pt-1">
        <span className="grid size-9 place-items-center rounded-xl bg-primary text-sm font-semibold text-primary-foreground" aria-hidden>B</span>
        <div className="leading-tight">
          <p className="text-sm font-semibold">BMW</p>
          <p className="text-xs text-muted-foreground">Product Intelligence</p>
        </div>
      </div>

      <Button onClick={() => go('research')} className="h-10 w-full justify-start gap-2 rounded-xl px-3 shadow-sm">
        <Plus /> New chat
      </Button>

      <nav aria-label="Main" className="flex flex-col gap-0.5">
        {NAV.map(({ id, label, Icon }) => (
          <a key={id} href={`#${id}`} aria-current={id === page ? 'page' : undefined}
            onClick={(e) => { e.preventDefault(); go(id, id === 'research' ? activeId : null) }}
            className={cn('flex h-9 items-center gap-2.5 rounded-xl px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
              id === page ? 'bg-sidebar-accent font-medium text-foreground' : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground')}>
            <Icon className="size-4" /> {label}
          </a>
        ))}
      </nav>

      <p className="px-3 pt-2 text-sm font-semibold">Chats</p>
      <ScrollArea className="-mx-1 min-h-0 flex-1">
        <div className="flex flex-col gap-3 px-1 pb-2">
          {listLoading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full rounded-lg" />)}
          {listError && <p role="alert" className="px-2 text-sm text-destructive">{`Chats unavailable: ${listError}`}</p>}
          {!listLoading && !listError && list.length === 0 && <p className="px-2 text-sm text-muted-foreground">No conversations yet.</p>}
          {group(list).map((g) => (
            <section key={g.label} aria-label={g.label}>
              <h2 className="px-2 pb-1 text-xs text-muted-foreground">{g.label}</h2>
              <ul className="flex flex-col gap-0.5">
                {g.items.map((c) => {
                  const active = page === 'research' && activeId === c.id
                  return (
                    <li key={c.id}>
                      <button type="button" onClick={() => go('research', c.id)} aria-current={active ? 'true' : undefined} title={c.title}
                        className={cn('w-full truncate rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                          active ? 'bg-sidebar-accent font-medium' : 'text-foreground/80 hover:bg-sidebar-accent/60')}>
                        {c.title}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
      </ScrollArea>

      <div className="flex items-center gap-1 border-t border-sidebar-border pt-3">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl p-1.5 text-left outline-none hover:bg-sidebar-accent/60 focus-visible:ring-2 focus-visible:ring-ring">
            <Avatar className="size-8"><AvatarFallback className="bg-accent text-xs font-medium text-accent-foreground">{initials(user?.display_name ?? '')}</AvatarFallback></Avatar>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-medium">{user?.display_name ?? 'Account'}</span>
              <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-60 rounded-xl">
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{user?.email}</DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut}><LogOut /> Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="px-1.5"><HealthBadge /></div>
    </div>
  )
}
