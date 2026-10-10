import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Search as SearchIcon, SlidersHorizontal, BarChart3, FileSearch } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { HitCard } from '@/components/evidence/HitCard'
import { FilterSelect } from '@/components/evidence/FilterSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import type {
  EvidenceFilters,
  FilterOptions,
  GroupBy,
  Hit,
  Line,
  Market,
  Polarity,
  Powertrain,
  SearchSource,
  StatsResponse,
} from '@/types/api'

const SOURCES: { value: SearchSource; label: string }[] = [
  { value: 'feedback', label: 'Customer feedback' },
  { value: 'docs', label: 'Catalog PDFs' },
]
const GROUPS: { value: GroupBy; label: string }[] = [
  { value: 'market_code', label: 'Market' },
  { value: 'vehicle_line', label: 'Vehicle line' },
  { value: 'domain', label: 'Domain' },
  { value: 'polarity', label: 'Polarity' },
  { value: 'powertrain', label: 'Powertrain' },
  { value: 'country', label: 'Country' },
  { value: 'feedback_type', label: 'Feedback type' },
]

type Load<T> = { kind: 'idle' } | { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: T }

const message = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')
const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'

export function EvidencePage() {
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [source, setSource] = useState<SearchSource>('feedback')
  const [filters, setFilters] = useState<EvidenceFilters>({})
  const [groupBy, setGroupBy] = useState<GroupBy>('market_code')
  const [results, setResults] = useState<Load<{ query: string; hits: Hit[] }>>({ kind: 'idle' })
  // Loading is derived: a result only counts if it was fetched for the current group and filters.
  const [statsDone, setStatsDone] = useState<{ key: string; result: Load<StatsResponse> } | null>(null)
  const statsKey = JSON.stringify([groupBy, filters])
  const stats: Load<StatsResponse> = statsDone?.key === statsKey ? statsDone.result : { kind: 'loading' }
  const searchCtrl = useRef<AbortController | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    api.filters(ctrl.signal).then(setOptions).catch((e) => !aborted(e) && setOptionsError(message(e)))
    return () => ctrl.abort()
  }, [])

  // Counts follow the filters; they are exact SQL counts, not a sample of the search results.
  useEffect(() => {
    const ctrl = new AbortController()
    api
      .stats(groupBy, filters, ctrl.signal)
      .then((data) => setStatsDone({ key: statsKey, result: { kind: 'ok', data } }))
      .catch((e) => !aborted(e) && setStatsDone({ key: statsKey, result: { kind: 'error', message: message(e) } }))
    return () => ctrl.abort()
  }, [groupBy, filters, statsKey])

  const set = <K extends keyof EvidenceFilters>(key: K, value: EvidenceFilters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }))

  function onSearch(e: FormEvent) {
    e.preventDefault()
    const text = q.trim()
    if (text.length < 2) return
    searchCtrl.current?.abort()
    const ctrl = new AbortController()
    searchCtrl.current = ctrl
    setResults({ kind: 'loading' })
    api
      .search(text, source, filters, ctrl.signal)
      .then((r) => setResults({ kind: 'ok', data: { query: r.query, hits: r.hits } }))
      .catch((e) => !aborted(e) && setResults({ kind: 'error', message: message(e) }))
  }

  return (
    <PageShell title="Evidence" Icon={SearchIcon} description="Search customer feedback and catalog text. Every result cites its file, location and quote.">
      <form onSubmit={onSearch} className="flex flex-col gap-4 rounded-2xl border border-border bg-background p-5 shadow-xs">
        <div className="grid gap-4 md:grid-cols-[1fr_220px]">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="live-q">Search</Label>
            <Input
              id="live-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="For example: seat ventilation too weak"
              minLength={2}
              required
            />
          </div>
          <FilterSelect
            id="live-source"
            label="Source"
            value={source}
            options={SOURCES}
            onChange={(v) => setSource((v as SearchSource) ?? 'feedback')}
            allLabel="Customer feedback"
          />
        </div>
        {optionsError && (
          <p role="alert" className="text-sm text-destructive">{`Filters unavailable: ${optionsError}`}</p>
        )}
        <p className="flex items-center gap-2 text-xs font-medium text-muted-foreground"><SlidersHorizontal className="size-3.5" /> Filters</p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <FilterSelect id="live-line" label="Vehicle line" value={filters.line}
            options={(options?.lines ?? []).map((v) => ({ value: v, label: v }))}
            onChange={(v) => set('line', v as Line | undefined)} />
          <FilterSelect id="live-market" label="Market" value={filters.market}
            options={(options?.markets ?? []).map((m) => ({ value: m.key, label: m.label }))}
            onChange={(v) => set('market', v as Market | undefined)} />
          <FilterSelect id="live-domain" label="Domain" value={filters.domain}
            options={(options?.domains ?? []).map((d) => ({ value: d.key, label: d.label }))}
            onChange={(v) => set('domain', v)} />
          <FilterSelect id="live-polarity" label="Polarity" value={filters.polarity}
            options={(options?.polarities ?? []).map((v) => ({ value: v, label: v }))}
            onChange={(v) => set('polarity', v as Polarity | undefined)} />
          <FilterSelect id="live-powertrain" label="Powertrain" value={filters.powertrain}
            options={(options?.powertrains ?? []).map((v) => ({ value: v, label: v }))}
            onChange={(v) => set('powertrain', v as Powertrain | undefined)} />
        </div>
        {source === 'docs' && (
          <p className="text-sm text-muted-foreground">
            Catalog search uses the vehicle line only. The catalogs are German, so German terms match best.
          </p>
        )}
        <div>
          <Button type="submit" size="lg" disabled={q.trim().length < 2 || results.kind === 'loading'}>
            <SearchIcon /> Search
          </Button>
        </div>
      </form>

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <section aria-labelledby="results-h" aria-live="polite" className="flex flex-col gap-4">
          <h2 id="results-h" className="flex items-center gap-2 text-lg"><FileSearch className="size-5 text-primary" /> Results</h2>
          {results.kind === 'idle' && (
            <p className="rounded-2xl border border-dashed border-input p-8 text-center text-muted-foreground">Enter a question above to see cited evidence.</p>
          )}
          {results.kind === 'loading' && (
            <div className="flex flex-col gap-4" aria-label="Loading results">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 w-full rounded-2xl" />)}
            </div>
          )}
          {results.kind === 'error' && (
            <p role="alert" className="rounded-2xl border border-destructive p-4 text-destructive">{results.message}</p>
          )}
          {results.kind === 'ok' && results.data.hits.length === 0 && (
            <p className="rounded-2xl border border-dashed border-input p-8 text-center text-muted-foreground">No matching evidence. Try fewer filters or different words.</p>
          )}
          {results.kind === 'ok' && results.data.hits.map((h) => <HitCard key={h.citation.id} hit={h} />)}
        </section>

        <aside aria-labelledby="counts-h" className="flex flex-col gap-4 self-start rounded-2xl border border-border bg-background p-5 shadow-xs">
          <h2 id="counts-h" className="flex items-center gap-2 text-lg"><BarChart3 className="size-5 text-primary" /> Counts</h2>
          <FilterSelect id="live-group" label="Group by" value={groupBy} options={GROUPS}
            onChange={(v) => setGroupBy((v as GroupBy) ?? 'market_code')} allLabel="Market" />
          {stats.kind === 'loading' && <Skeleton className="h-32 w-full rounded-xl" aria-label="Loading counts" />}
          {stats.kind === 'error' && <p role="alert" className="text-sm text-destructive">{stats.message}</p>}
          {stats.kind === 'ok' && (
            <table className="w-full text-sm">
              <caption className="sr-only">Comment counts by group</caption>
              <thead>
                <tr className="border-b border-border text-left text-xs tracking-wide text-muted-foreground">
                  <th scope="col" className="py-2 font-normal">Group</th>
                  <th scope="col" className="py-2 text-right font-normal">Comments</th>
                </tr>
              </thead>
              <tbody>
                {stats.data.rows.map((r) => (
                  <tr key={r.key ?? 'none'} className="border-b border-border">
                    <td className="py-2">{r.key ?? 'Not classified'}</td>
                    <td className="py-2 text-right tabular-nums">{r.n.toLocaleString('en-US')}</td>
                  </tr>
                ))}
                <tr>
                  <th scope="row" className="py-2 text-left font-bold">Total</th>
                  <td className="py-2 text-right font-bold tabular-nums">{stats.data.total.toLocaleString('en-US')}</td>
                </tr>
              </tbody>
            </table>
          )}
        </aside>
      </div>
    </PageShell>
  )
}
