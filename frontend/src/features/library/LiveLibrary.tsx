import { useCallback, useEffect, useMemo, useState } from 'react'
import { Database, FileText, Globe, Grid3x3, Waypoints } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import type { Coverage, SourceGraph as GraphData, SourceInfo, WebFind } from '@/types/api'
import { CoverageTab } from './CoverageTab'
import { FilesTab } from './FilesTab'
import { errorText, fmt, isWeb, type Load } from './format'
import { SourceGraph } from './SourceGraph'
import { WebsitesTab } from './WebsitesTab'

type Tab = 'graph' | 'files' | 'websites' | 'coverage'
const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-0.5 bg-background px-5 py-4">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted-foreground">{note}</dd>}
    </div>
  )
}

const Unavailable = ({ what, message }: { what: string; message: string }) => (
  <p role="alert" className="rounded-2xl border border-destructive bg-background p-4 text-sm text-destructive">{`${what} unavailable: ${message}`}</p>
)

export function LiveLibrary() {
  const [tab, setTab] = useState<Tab>('graph')
  const [sources, setSources] = useState<Load<SourceInfo[]>>({ kind: 'loading' })
  const [coverage, setCoverage] = useState<Load<Coverage>>({ kind: 'loading' })
  const [graph, setGraph] = useState<Load<GraphData>>({ kind: 'loading' })
  const [found, setFound] = useState<Load<WebFind[]>>({ kind: 'loading' })

  // Also called after a file or website is added or removed: the views then change in place, without going
  // back to the loading state.
  const load = useCallback((signal?: AbortSignal) => {
    const into = <T,>(set: (l: Load<T>) => void) => [
      (data: T) => set({ kind: 'ok', data }),
      (e: unknown) => { if (!aborted(e)) set({ kind: 'error', message: errorText(e) }) },
    ] as const
    api.sources(signal).then(...into(setSources))
    api.coverage(signal).then(...into(setCoverage))
    api.sourceGraph(signal).then(...into(setGraph))
    api.webResearch(signal).then(...into(setFound))
  }, [])

  useEffect(() => {
    const ctrl = new AbortController()
    load(ctrl.signal)
    return () => ctrl.abort()
  }, [load])

  const cells = coverage.kind === 'ok' ? coverage.data.cells : null
  const lines = useMemo(() => [...new Set((cells ?? []).map((c) => c.line))], [cells])
  const markets = useMemo(() => [...new Set((cells ?? []).map((c) => c.market))], [cells])
  const all = sources.kind === 'ok' ? sources.data : null
  const files = useMemo(() => (all ?? []).filter((s) => !isWeb(s)), [all])
  const websites = useMemo(() => (all ?? []).filter(isWeb), [all])
  const noFinds = useMemo<WebFind[]>(() => [], [])
  const gaps = (cells ?? []).filter((c) => c.feedback === 0).length
  const read = found.kind === 'ok' ? found.data.filter((w) => !w.source_id).length : 0
  const loading = <Skeleton className="h-64 w-full rounded-2xl" aria-label="Loading sources" />

  return (
    <PageShell testId="live-library" title="Sources" Icon={Database} description="Everything the agents can cite: files, websites, and what they cover per vehicle line and market.">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border shadow-xs lg:grid-cols-4" aria-label="Summary">
        <Stat label="Files" value={all ? fmt(files.length) : '–'} />
        <Stat label="Websites" value={all ? fmt(websites.length) : '–'} note={read ? `${fmt(read)} more read by agents` : undefined} />
        <Stat label="Customer comments" value={coverage.kind === 'ok' ? fmt(coverage.data.total_feedback) : '–'} />
        <Stat label="Gaps" value={cells ? fmt(gaps) : '–'} note={cells ? `of ${cells.length} line and market pairs have no customer feedback` : undefined} />
      </dl>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList aria-label="Sources views">
          <TabsTrigger value="graph"><Waypoints aria-hidden /> Graph</TabsTrigger>
          <TabsTrigger value="files"><FileText aria-hidden /> Files</TabsTrigger>
          <TabsTrigger value="websites"><Globe aria-hidden /> Websites</TabsTrigger>
          <TabsTrigger value="coverage"><Grid3x3 aria-hidden /> Coverage</TabsTrigger>
        </TabsList>

        <TabsContent value="graph">
          {(sources.kind === 'loading' || graph.kind === 'loading' || coverage.kind === 'loading') && loading}
          {sources.kind === 'error' && <Unavailable what="Sources" message={sources.message} />}
          {graph.kind === 'error' && sources.kind !== 'error' && <Unavailable what="Graph" message={graph.message} />}
          {coverage.kind === 'error' && sources.kind !== 'error' && <Unavailable what="Coverage" message={coverage.message} />}
          {sources.kind === 'ok' && graph.kind === 'ok' && coverage.kind === 'ok' && (
            <SourceGraph sources={sources.data} links={graph.data.links} found={found.kind === 'ok' ? found.data : noFinds}
              lines={lines} markets={markets} onShow={setTab} />
          )}
        </TabsContent>

        <TabsContent value="files">
          {sources.kind === 'loading' && loading}
          {sources.kind === 'error' && <Unavailable what="Sources" message={sources.message} />}
          {sources.kind === 'ok' && <FilesTab files={files} lines={lines} onStored={load} />}
        </TabsContent>

        <TabsContent value="websites">
          {sources.kind === 'loading' && loading}
          {sources.kind === 'error' && <Unavailable what="Sources" message={sources.message} />}
          {sources.kind === 'ok' && <WebsitesTab websites={websites} found={found} lines={lines} markets={markets} onChanged={load} />}
        </TabsContent>

        <TabsContent value="coverage">
          {coverage.kind === 'loading' && loading}
          {coverage.kind === 'error' && <Unavailable what="Coverage" message={coverage.message} />}
          {coverage.kind === 'ok' && <CoverageTab coverage={coverage.data} />}
        </TabsContent>
      </Tabs>
    </PageShell>
  )
}
