import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Check, Flag, RotateCcw, ShieldQuestion, X, Archive, Eye, type LucideIcon } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { CitationChip } from '@/features/sources/CitationChip'
import { findingsFrom, indexOf, statementRefs } from '@/features/sources/citations'
import { ApiError } from '@/lib/api'
import type { DecisionAction, Requirement, RequirementStatus, Statement } from '@/types/api'

export const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'
export const messageOf = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

export type Load<T> = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: T }

/** Loads once, and again on `reload()`. A reload keeps the old data on screen instead of flashing a skeleton. */
export function useLoad<T>(fetcher: (signal: AbortSignal) => Promise<T>): [Load<T>, () => void] {
  const [state, setState] = useState<Load<T>>({ kind: 'loading' })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const ctrl = new AbortController()
    fetcher(ctrl.signal).then((data) => setState({ kind: 'ok', data }))
      .catch((e) => !aborted(e) && setState({ kind: 'error', message: messageOf(e) }))
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick])
  return [state, useCallback(() => setTick((t) => t + 1), [])]
}

export const STATUS_LABEL: Record<RequirementStatus, string> = {
  draft: 'Needs review', pm_review: 'Needs review', tracked: 'Tracked', rejected: 'Rejected',
  challenged: 'Challenged', superseded: 'Superseded',
}

export function StatusBadge({ status }: { status: RequirementStatus }) {
  const variant = status === 'tracked' ? 'default' : status === 'rejected' ? 'destructive' : 'outline'
  return <Badge variant={variant}>{STATUS_LABEL[status]}</Badge>
}

const TIER_SHORT: [RegExp, string][] = [[/^Tier 1/, 'Tier 1'], [/^Tier 2/, 'Tier 2'], [/^Tier 3/, 'Tier 3']]
export const tierShort = (tier: string) => TIER_SHORT.find(([re]) => re.test(tier))?.[1] ?? tier
export const tierFor = (composite: number) => (composite >= 0.65 ? 'Tier 1' : composite >= 0.4 ? 'Tier 2' : 'Tier 3')
export const TIER_HELP: Record<string, string> = { 'Tier 1': 'must-have', 'Tier 2': 'should-have', 'Tier 3': 'watch-list' }

export const pct = (v: number) => `${Math.round(v * 100)}%`

/** Statement text followed by numbered source chips that open the cited row. */
export function Cited({ statement, req }: { statement: Statement; req: Requirement }) {
  const index = indexOf(findingsFrom(req.evidence))
  const refs = statementRefs(statement.citations ?? [], index)
  return (
    <>
      {statement.text}
      {refs.map((r, i) => <CitationChip key={i} n={i + 1} sourceRef={r} />)}
    </>
  )
}

const ACTION_UI: Record<DecisionAction, { label: string; Icon: LucideIcon; variant: 'default' | 'outline' | 'ghost'; ask?: { title: string; help: string; required: boolean; done: string } }> = {
  approve: { label: 'Approve and track', Icon: Check, variant: 'default' },
  reject: { label: 'Reject', Icon: X, variant: 'outline',
    ask: { title: 'Reject this requirement', help: 'Say why, so the team can see the reasoning later.', required: true, done: 'Reject' } },
  challenge: { label: 'Challenge', Icon: ShieldQuestion, variant: 'outline',
    ask: { title: 'Challenge this requirement', help: 'What evidence or clarification is missing?', required: true, done: 'Challenge' } },
  supersede: { label: 'Supersede', Icon: Archive, variant: 'outline',
    ask: { title: 'Supersede this requirement', help: 'What replaces it, or why is it no longer needed?', required: true, done: 'Supersede' } },
  reopen: { label: 'Reopen as draft', Icon: RotateCcw, variant: 'outline' },
  acknowledge: { label: 'Mark as reviewed', Icon: Eye, variant: 'outline',
    ask: { title: 'Mark flags as reviewed', help: 'Optional note. The requirement stays tracked and the flags are cleared.', required: false, done: 'Mark as reviewed' } },
}

/** The buttons for the decisions a requirement accepts. Reasons are asked in a dialog; every decision is recorded. */
export function DecisionButtons({ req, only, onDecide }: { req: Requirement; only?: DecisionAction[]; onDecide: (id: string, action: DecisionAction, note?: string) => Promise<void> }) {
  const [asking, setAsking] = useState<DecisionAction | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const actions = req.actions.filter((a) => !only || only.includes(a))

  const run = async (action: DecisionAction, text?: string) => {
    setBusy(true); setError(null)
    try { await onDecide(req.id, action, text); setAsking(null); setNote('') }
    catch (e) { setError(messageOf(e)) }
    finally { setBusy(false) }
  }
  const click = (a: DecisionAction) => (ACTION_UI[a].ask ? (setError(null), setAsking(a)) : run(a))
  const ask = asking ? ACTION_UI[asking].ask : undefined

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {actions.map((a) => {
          const { label, Icon, variant } = ACTION_UI[a]
          return <Button key={a} size="lg" variant={variant} disabled={busy} onClick={() => click(a)} className="rounded-xl"><Icon aria-hidden /> {label}</Button>
        })}
        {!asking && error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </div>
      <Dialog open={asking !== null} onOpenChange={(o) => !o && setAsking(null)}>
        <DialogContent className="rounded-2xl sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{ask?.title}</DialogTitle>
            <DialogDescription>{`${req.code}: ${req.title}`}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`note-${req.id}`}>{ask?.required ? 'Reason' : 'Note (optional)'}</Label>
            <Textarea id={`note-${req.id}`} value={note} onChange={(e) => setNote(e.target.value)} rows={3} className="rounded-xl" />
            <p className="text-xs text-muted-foreground">{ask?.help}</p>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAsking(null)}>Cancel</Button>
            <Button disabled={busy || (ask?.required && !note.trim())} onClick={() => asking && run(asking, note.trim() || undefined)}>{ask?.done}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

/** Where the PM is in BMW's process, with one click to each place. Counts show what is waiting. */
export function ProcessStrip({ current, counts }: { current: 'research' | 'requirements' | 'priorities' | 'tracking' | 'dossiers'; counts?: { review?: number; tracked?: number; flags?: number } }) {
  const steps: { id: typeof current; label: string; href: string; badge?: ReactNode }[] = [
    { id: 'research', label: 'Research', href: '#research' },
    { id: 'requirements', label: 'Review', href: '#requirements', badge: counts?.review ? counts.review : undefined },
    { id: 'priorities', label: 'Prioritize', href: '#requirements?tab=priorities' },
    { id: 'tracking', label: 'Track', href: '#tracking', badge: counts?.flags ? <Flag className="size-3" aria-label="has flags" /> : undefined },
    { id: 'dossiers', label: 'Document', href: '#dossiers' },
  ]
  return (
    <nav aria-label="Process" className="flex flex-wrap items-center gap-1 rounded-2xl border border-border bg-card p-1 shadow-xs">
      {steps.map((s, i) => (
        <a key={s.id} href={s.href} aria-current={s.id === current ? 'step' : undefined}
          className={`flex h-9 items-center gap-2 rounded-xl px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring ${s.id === current ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>
          <span className="grid size-5 place-items-center rounded-full border border-current text-xs" aria-hidden>{i + 1}</span>
          {s.label}
          {s.badge !== undefined && <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{s.badge}</span>}
        </a>
      ))}
    </nav>
  )
}
