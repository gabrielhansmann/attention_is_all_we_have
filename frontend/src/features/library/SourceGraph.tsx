import { useMemo, useState, type KeyboardEvent, type ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { SourceInfo, SourceLink, WebFind } from '@/types/api'
import { clip, contents, domainOf, fmt, fmtDate, isWeb, tierLabel } from './format'

type Kind = 'file' | 'website' | 'found' | 'line' | 'market'

interface GraphNode {
  id: string
  kind: Kind
  label: string
  rows: number
  x: number
  y: number
  r: number
  source?: SourceInfo
  find?: WebFind
}

interface Edge {
  id: string
  from: string
  to: string
  rows: number
  planned: boolean        // an agent read the page for this line: no stored rows behind the link
  sources: Set<string>
  markets: Set<string>
}

interface Triple { source: string; line: string | null; market: string | null; rows: number; planned: boolean }

interface Props {
  sources: SourceInfo[]
  links: SourceLink[]
  found: WebFind[]
  lines: string[]
  markets: string[]
  onShow: (tab: 'files' | 'websites' | 'coverage') => void
}

// Geometry of the drawing, in SVG units (1 unit = 1px at full width).
const W = 960
const X = { source: 340, line: 610, market: 860 }
const ROW = 40
const CAPTION = 30
const TOP = 44
const MIN_SPAN = 260
const PILL = { w: 84, h: 32 }
const MAX_FOUND = 10      // agent-read pages drawn; the rest are listed in the Websites tab
const LABEL_CHARS = 40

const KIND_LABEL: Record<Kind, string> = {
  file: 'File', website: 'Stored website', found: 'Website read by an agent', line: 'Vehicle line', market: 'Market',
}

function build({ sources, links, found, lines, markets }: Omit<Props, 'onShow'>) {
  const triples: Triple[] = links.map((l) => ({ source: `s:${l.source_id}`, line: l.line, market: l.market, rows: l.rows, planned: false }))
  const unstored = found.filter((w) => !w.source_id)
  const drawn = unstored.slice(0, MAX_FOUND)
  for (const w of drawn) if (w.vehicle_line) triples.push({ source: `w:${w.url}`, line: w.vehicle_line, market: w.market, rows: 0, planned: true })

  const rowsOf = (id: string) => triples.filter((t) => t.source === id).reduce((n, t) => n + t.rows, 0)
  const maxRows = Math.max(1, ...sources.map((s) => rowsOf(`s:${s.id}`)))
  const nodes: GraphNode[] = []
  const captions: { label: string; y: number }[] = []
  let y = TOP
  const group = (label: string, items: Omit<GraphNode, 'x' | 'y' | 'r'>[]) => {
    if (!items.length) return
    captions.push({ label, y: y + CAPTION / 2 })
    y += CAPTION
    for (const item of items) {
      nodes.push({ ...item, x: X.source, y: y + ROW / 2, r: item.kind === 'found' ? 6 : 5 + 11 * Math.sqrt(item.rows / maxRows) })
      y += ROW
    }
  }
  const sourceNode = (s: SourceInfo): Omit<GraphNode, 'x' | 'y' | 'r'> => ({
    id: `s:${s.id}`, kind: isWeb(s) ? 'website' : 'file', rows: rowsOf(`s:${s.id}`), source: s,
    label: isWeb(s) ? s.title || domainOf(s.file) : s.file,
  })
  group('Files', sources.filter((s) => !isWeb(s)).map(sourceNode))
  group('Stored websites', sources.filter(isWeb).map(sourceNode))
  group('Read by agents, not stored', drawn.map((w) => ({ id: `w:${w.url}`, kind: 'found' as const, rows: 0, find: w, label: w.title || w.domain })))

  const span = Math.max(y - TOP, MIN_SPAN)
  const spread = (keys: string[], kind: 'line' | 'market', x: number) => keys.forEach((key, i) => nodes.push({
    id: `${kind[0]}:${key}`, kind, label: key, x, y: TOP + ((i + 0.5) * span) / keys.length, r: 0,
    rows: triples.filter((t) => (kind === 'line' ? t.line : t.market) === key).reduce((n, t) => n + t.rows, 0),
  }))
  spread(lines, 'line', X.line)
  spread(markets, 'market', X.market)

  const known = new Set(nodes.map((n) => n.id))
  const edges = new Map<string, Edge>()
  const add = (from: string, to: string, t: Triple) => {
    if (!known.has(from) || !known.has(to)) return
    const id = `${from}>${to}`
    const e = edges.get(id) ?? { id, from, to, rows: 0, planned: true, sources: new Set(), markets: new Set() }
    e.rows += t.rows
    e.planned = e.planned && t.planned
    e.sources.add(t.source)
    if (t.market) e.markets.add(`m:${t.market}`)
    edges.set(id, e)
  }
  for (const t of triples) {
    if (t.line) add(t.source, `l:${t.line}`, t)
    if (t.line && t.market && !t.planned) add(`l:${t.line}`, `m:${t.market}`, t)
    if (!t.line && t.market) add(t.source, `m:${t.market}`, t)
  }
  return { nodes, captions, edges: [...edges.values()], triples, height: TOP + span + 16, hidden: unstored.length - drawn.length }
}

function path(a: GraphNode, b: GraphNode): string {
  const x1 = a.x + (a.kind === 'line' ? PILL.w / 2 : a.r)
  const x2 = b.x - PILL.w / 2
  const mid = (x1 + x2) / 2
  return `M${x1},${a.y} C${mid},${a.y} ${mid},${b.y} ${x2},${b.y}`
}

const fill = (kind: Kind) => (kind === 'file' ? 'var(--source-file)' : 'var(--source-web)')

/** Sources on the left, the vehicle lines they cover in the middle, the markets on the right.
 *  Circle size and line width show how many rows of evidence are behind a source or a link. */
export function SourceGraph(props: Props) {
  const { sources, links, found, lines, markets, onShow } = props
  const g = useMemo(() => build({ sources, links, found, lines, markets }), [sources, links, found, lines, markets])
  const [selected, setSelected] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const activeId = hover ?? selected
  const byId = useMemo(() => new Map(g.nodes.map((n) => [n.id, n])), [g])
  const active = activeId ? byId.get(activeId) : undefined

  // A link belongs to the active node when it touches it, carries rows of that source, or leads to that market.
  const lit = (e: Edge) => !activeId || e.from === activeId || e.to === activeId || e.sources.has(activeId) || e.markets.has(activeId)
  const litNodes = activeId ? new Set([activeId, ...g.edges.filter(lit).flatMap((e) => [e.from, e.to])]) : null
  const maxEdge = Math.max(1, ...g.edges.map((e) => e.rows))

  const interactive = (n: GraphNode) => ({
    role: 'button', tabIndex: 0, 'aria-pressed': selected === n.id,
    'aria-label': `${n.label}, ${KIND_LABEL[n.kind].toLowerCase()}${n.rows ? `, ${fmt(n.rows)} rows` : ''}`,
    onMouseEnter: () => setHover(n.id), onMouseLeave: () => setHover(null),
    onFocus: () => setHover(n.id), onBlur: () => setHover(null),
    onClick: () => setSelected((s) => (s === n.id ? null : n.id)),
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected((s) => (s === n.id ? null : n.id)) }
      if (e.key === 'Escape') setSelected(null)
    },
  } as const)

  if (!sources.length && !g.nodes.some((n) => n.kind === 'found')) {
    return <p className="rounded-2xl border border-border bg-background p-6 text-sm text-muted-foreground">No sources are loaded yet. Add a file or a website to see what it covers.</p>
  }

  return (
    <div className="grid overflow-hidden rounded-2xl border border-border bg-background shadow-xs lg:grid-cols-[minmax(0,1fr)_19rem]" data-testid="source-graph">
      <div className="flex min-w-0 flex-col">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Source graph, scrolls sideways on small screens">
          <svg viewBox={`0 0 ${W} ${g.height}`} width={W} height={g.height} className="block h-auto w-full min-w-[760px] select-none" role="group"
            aria-label="Graph of sources, the vehicle lines they cover and the markets">
            {[['Sources', X.source, 'end'], ['Vehicle lines', X.line, 'middle'], ['Markets', X.market, 'middle']].map(([label, x, anchor]) => (
              <text key={label} x={x} y={22} textAnchor={anchor as 'end' | 'middle'} className="fill-muted-foreground text-[11px] font-semibold tracking-wider uppercase">{label}</text>
            ))}
            {g.captions.map((c) => (
              <text key={c.label} x={X.source - 26} y={c.y + 6} textAnchor="end" className="fill-muted-foreground text-[11px]">{c.label}</text>
            ))}

            <g fill="none" strokeLinecap="round">
              {g.edges.map((e) => {
                const on = lit(e)
                return (
                  <path key={e.id} d={path(byId.get(e.from)!, byId.get(e.to)!)}
                    stroke={active && on ? 'var(--foreground)' : '#aab1bd'}
                    strokeOpacity={active ? (on ? 0.55 : 0.12) : 0.45}
                    strokeWidth={e.planned ? 1.5 : 1.5 + 8.5 * Math.sqrt(e.rows / maxEdge)}
                    strokeDasharray={e.planned ? '4 5' : undefined} className="transition-[stroke-opacity]" />
                )
              })}
            </g>

            {g.nodes.map((n) => {
              const dim = litNodes && !litNodes.has(n.id)
              const ring = activeId === n.id || selected === n.id
              if (n.kind === 'line' || n.kind === 'market') {
                return (
                  <g key={n.id} {...interactive(n)} opacity={dim ? 0.3 : 1} className="cursor-pointer outline-none transition-opacity">
                    <rect x={n.x - PILL.w / 2 - 4} y={n.y - PILL.h / 2 - 6} width={PILL.w + 8} height={PILL.h + 12} fill="transparent" />
                    <rect x={n.x - PILL.w / 2} y={n.y - PILL.h / 2} width={PILL.w} height={PILL.h} rx={10}
                      fill={n.rows ? 'var(--surface-dark)' : 'var(--background)'} stroke={ring ? 'var(--ring)' : n.rows ? 'var(--surface-dark)' : 'var(--input)'}
                      strokeWidth={ring ? 3 : 1.5} strokeDasharray={n.rows || ring ? undefined : '4 4'} />
                    <text x={n.x} y={n.y + 4.5} textAnchor="middle" className={cn('text-[13px] font-semibold', n.rows ? 'fill-on-dark' : 'fill-muted-foreground')}>{n.label}</text>
                  </g>
                )
              }
              return (
                <g key={n.id} {...interactive(n)} opacity={dim ? 0.3 : 1} className="cursor-pointer outline-none transition-opacity">
                  <rect x={0} y={n.y - ROW / 2} width={n.x + 22} height={ROW} fill="transparent" />
                  {ring && <circle cx={n.x} cy={n.y} r={n.r + 4} fill="none" stroke="var(--ring)" strokeWidth={2} />}
                  <circle cx={n.x} cy={n.y} r={n.r} fill={n.kind === 'found' ? 'var(--background)' : fill(n.kind)}
                    stroke={n.kind === 'found' ? 'var(--source-web)' : 'var(--background)'} strokeWidth={2} />
                  <text x={n.x - 26} y={n.y + 4.5} textAnchor="end" className={cn('fill-foreground text-[13px]', ring && 'font-semibold')}>
                    {clip(n.label, LABEL_CHARS)}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
        <ul className="flex flex-wrap gap-x-5 gap-y-2 border-t border-border px-4 py-3 text-xs text-muted-foreground" aria-label="Legend">
          <li className="flex items-center gap-2"><span className="size-3 rounded-full bg-source-file" aria-hidden /> File</li>
          <li className="flex items-center gap-2"><span className="size-3 rounded-full bg-source-web" aria-hidden /> Stored website</li>
          <li className="flex items-center gap-2"><span className="size-3 rounded-full border-2 border-source-web bg-background" aria-hidden /> Website read by an agent, not stored</li>
          <li>A larger circle or a thicker line means more rows of evidence.</li>
          {g.hidden > 0 && <li>{`${g.hidden} more agent websites are listed in the Websites tab.`}</li>}
        </ul>
      </div>
      <Details node={active} graph={g} byId={byId} pinned={!!selected && selected === active?.id} lines={lines} markets={markets} onShow={onShow} />
    </div>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">{children}</dd>
    </div>
  )
}

function Breakdown({ title, rows }: { title: string; rows: { key: string; rows: number; note?: string }[] }) {
  if (!rows.length) return null
  const max = Math.max(1, ...rows.map((r) => r.rows))
  return (
    <div className="flex flex-col gap-2">
      <h4 className="text-xs font-normal text-muted-foreground">{title}</h4>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.key} className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-2 text-sm">
            <span className="truncate" title={r.key}>{r.key}</span>
            <span className="h-1.5 rounded-full bg-muted" aria-hidden>
              <span className="block h-full rounded-full bg-foreground/70" style={{ width: `${r.rows ? Math.max(3, (r.rows / max) * 100) : 0}%` }} />
            </span>
            <span className={cn('tabular-nums', !r.rows && 'text-muted-foreground')}>{r.rows ? fmt(r.rows) : r.note ?? 'No rows'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Details({ node, graph, byId, pinned, lines, markets, onShow }: {
  node?: GraphNode; graph: ReturnType<typeof build>; byId: Map<string, GraphNode>; pinned: boolean
  lines: string[]; markets: string[]; onShow: Props['onShow']
}) {
  const shell = 'flex flex-col gap-4 border-t border-border bg-canvas-tint/60 p-5 lg:border-t-0 lg:border-l'
  if (!node) {
    return (
      <aside className={shell} aria-label="Details" aria-live="polite">
        <h3 className="text-sm">What is behind a node</h3>
        <p className="text-sm text-muted-foreground">
          Point at a source, a vehicle line or a market to follow its links. Select it to keep the details open.
        </p>
        <p className="text-sm text-muted-foreground">
          A vehicle line or market drawn with a dashed outline has no evidence at all.
        </p>
      </aside>
    )
  }
  const sum = (ts: Triple[]) => ts.reduce((n, t) => n + t.rows, 0)
  const stored = graph.triples.filter((t) => !t.planned)
  let body: ReactNode
  if (node.kind === 'line' || node.kind === 'market') {
    const mine = stored.filter((t) => (node.kind === 'line' ? t.line : t.market) === node.label)
    const other = node.kind === 'line' ? markets : lines
    const feeding = [...new Set(mine.map((t) => t.source))].map((id) => ({ key: byId.get(id)?.label ?? id, rows: sum(mine.filter((t) => t.source === id)) }))
      .sort((a, b) => b.rows - a.rows).slice(0, 6)
    body = (
      <>
        <dl className="flex flex-col gap-3"><Fact label="Rows of evidence">{node.rows ? fmt(node.rows) : 'None'}</Fact></dl>
        <Breakdown title={node.kind === 'line' ? 'By market' : 'By vehicle line'}
          rows={other.map((key) => ({ key, rows: sum(mine.filter((t) => (node.kind === 'line' ? t.market : t.line) === key)) }))} />
        <Breakdown title="Largest sources" rows={feeding} />
        <div><Button variant="outline" size="sm" onClick={() => onShow('coverage')}>Open coverage table</Button></div>
      </>
    )
  } else if (node.source) {
    const s = node.source
    const mine = stored.filter((t) => t.source === node.id)
    const scope = (t: Triple) => [t.line, t.market].filter(Boolean).join(', ') || 'General'
    const rows = [...new Set(mine.map(scope))].map((key) => ({ key, rows: sum(mine.filter((t) => scope(t) === key)) })).sort((a, b) => b.rows - a.rows).slice(0, 8)
    body = (
      <>
        <dl className="flex flex-col gap-3">
          {isWeb(s) && <Fact label="Address"><a href={s.file} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">{domainOf(s.file)} <ExternalLink className="size-3.5" aria-hidden /><span className="sr-only">(opens in a new tab)</span></a></Fact>}
          <Fact label="Kind">{isWeb(s) ? tierLabel(s.trust_tier) : s.family}</Fact>
          <Fact label="Contents">{contents(s.counts)}</Fact>
          {isWeb(s) && <Fact label="Fetched">{fmtDate(s.retrieved_at)}</Fact>}
        </dl>
        <Breakdown title="Rows by vehicle line and market" rows={rows} />
        <div><Button variant="outline" size="sm" onClick={() => onShow(isWeb(s) ? 'websites' : 'files')}>{isWeb(s) ? 'Open Websites tab' : 'Open Files tab'}</Button></div>
      </>
    )
  } else if (node.find) {
    const w = node.find
    body = (
      <>
        <dl className="flex flex-col gap-3">
          <Fact label="Address"><a href={w.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">{w.domain} <ExternalLink className="size-3.5" aria-hidden /><span className="sr-only">(opens in a new tab)</span></a></Fact>
          <Fact label="Read by">{`${w.agent}, ${fmtDate(w.retrieved_at)}`}</Fact>
          <Fact label="Result">{w.findings > 0 ? `${w.findings} ${w.findings === 1 ? 'finding' : 'findings'}` : w.skipped_reason ? `Read, not used: ${clip(w.skipped_reason, 120)}` : 'Read, not used'}</Fact>
          {w.request && <Fact label="Request">{clip(w.request, 140)}</Fact>}
        </dl>
        <p className="text-sm text-muted-foreground">Only a short snapshot is kept. Store the page to make its full text searchable.</p>
        <div><Button variant="outline" size="sm" onClick={() => onShow('websites')}>Open Websites tab</Button></div>
      </>
    )
  }
  return (
    <aside className={shell} aria-label="Details" aria-live="polite">
      <div>
        <p className="text-xs text-muted-foreground">{`${KIND_LABEL[node.kind]}${pinned ? ', selected' : ''}`}</p>
        <h3 className="mt-0.5 break-words text-base">{clip(node.label, 90)}</h3>
      </div>
      {body}
    </aside>
  )
}
