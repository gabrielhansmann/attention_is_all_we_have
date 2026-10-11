import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Car, ExternalLink, Loader2, Plus, RefreshCw } from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { SourceViewerProvider } from '@/features/sources/SourceViewer'
import { CitationChip } from '@/features/sources/CitationChip'
import { LiveResearch } from '@/features/research/LiveResearch'
import type { Comparison, Model, Observation, Overview } from './types'

const message = (e: unknown) => e instanceof ApiError ? e.message : 'The comparison could not be loaded.'
const fmt = (value: number) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(value)
const stamp = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const valueOf = (o: Observation) => o.text_value ?? `${fmt(o.value!)}${o.upper_value !== null ? `–${fmt(o.upper_value)}` : ''} ${o.unit}`

function Choice({ id, label, value, options, onChange, disabled = false }: { id: string; label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; disabled?: boolean }) {
  return <div className="min-w-0 space-y-1.5"><Label htmlFor={id}>{label}</Label><Select items={options} value={value} onValueChange={(v) => { if (v !== null) onChange(v) }} disabled={disabled}><SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger><SelectContent>{options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent></Select></div>
}

function SourceFact({ observation: o, busy, validate }: { observation: Observation; busy: boolean; validate: (mode: 'recrawl' | 'reevaluate', id: string) => void }) {
  return <div className="space-y-2 rounded-xl bg-muted/40 p-3 text-sm">
    <p className="flex flex-wrap items-center gap-1"><strong>{o.variant || 'Model family'}</strong><span>{valueOf(o)}</span><CitationChip n="Source" sourceRef={o.citation} /></p>
    <blockquote className="break-words border-l-2 border-border pl-3 text-xs text-muted-foreground">{o.quote}</blockquote>
    <p className="text-xs text-muted-foreground">Variant context: {o.scope_quote}</p>
    <p className="text-xs text-muted-foreground">{o.type === 'web' ? 'Crawled' : 'Dataset ingested'} <time dateTime={o.retrieved_at}>{stamp(o.retrieved_at)}</time>. Evaluated <time dateTime={o.extracted_at}>{stamp(o.extracted_at)}</time>.</p>
    <p className="text-xs text-muted-foreground">{[o.powertrain, o.standard, o.basis.replaceAll('_', ' '), o.period.replaceAll('_', ' ')].filter(Boolean).join(', ')}</p>
    {o.previous && <p className="text-xs">{o.changed ? 'Changed since the previous evaluation.' : 'Unchanged since the previous evaluation.'} Previous: {o.previous.text_value ?? `${o.previous.value}${o.previous.upper_value !== null ? `–${o.previous.upper_value}` : ''} ${o.unit}`} <CitationChip n="Previous source" sourceRef={o.previous.citation} /></p>}
    <div className="flex flex-wrap gap-2">
      {o.type === 'web' && <><a href={o.citation.file} target="_blank" rel="noreferrer noopener" className="inline-flex min-h-9 items-center gap-1 text-xs text-primary underline"><ExternalLink className="size-3" aria-hidden /> Open source</a><Button size="sm" variant="outline" disabled={busy} onClick={() => validate('recrawl', o.id)}>Recrawl source</Button></>}
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => validate('reevaluate', o.id)}>Reevaluate finding</Button>
    </div>
  </div>
}

function MetricChart({ comparison: c, name, busy, validate }: { comparison: Comparison; name: string; busy: boolean; validate: (mode: 'recrawl' | 'reevaluate', id: string) => void }) {
  const all = [c.own?.upper_value ?? c.own?.value ?? 0, c.mean_range?.upper ?? c.mean ?? 0, c.median_range?.upper ?? c.median ?? 0, ...c.contributors.map((o) => o.upper_value ?? o.value ?? 0)]
  const max = Math.max(...all, 1)
  const rows = [
    ...(c.own?.value !== null && c.own ? [{ label: name, value: c.own.value!, upper: c.own.upper_value, kind: 'own', citation: c.own.citation }] : []),
    ...c.contributors.map((o) => ({ label: `${o.name} ${o.variant}`, value: o.value!, upper: o.upper_value, kind: 'rival', citation: o.citation })),
    ...(c.median !== null || c.median_range ? [{ label: `Competitor median (n=${c.n})`, value: c.median_range?.lower ?? c.median!, upper: c.median_range?.upper ?? null, kind: 'median', citation: undefined }] : []),
    ...(c.mean !== null || c.mean_range ? [{ label: `Competitor mean (n=${c.n})`, value: c.mean_range?.lower ?? c.mean!, upper: c.mean_range?.upper ?? null, kind: 'mean', citation: undefined }] : []),
  ]
  return <article className="min-w-0 rounded-2xl border border-border bg-background p-4 shadow-xs" aria-label={`${c.label} comparison`}>
    <div className="mb-3 flex items-start justify-between gap-2"><h3 className="text-sm font-semibold">{c.label}</h3><span className="text-xs text-muted-foreground">{c.unit}{c.standard ? `, ${c.standard}` : ''}</span></div>
    <div className="space-y-2" role="group" aria-label={rows.map((r) => `${r.label}: ${r.value}${r.upper !== null ? ` to ${r.upper}` : ''} ${c.unit}`).join('; ') || 'No comparable numerical values'}>
      {rows.map((row, i) => <div key={`${row.kind}-${i}`} className="space-y-1">
        <div className="flex items-start justify-between gap-2 text-xs"><span className="min-w-0 break-words">{row.label}{row.citation && <CitationChip n="Source" sourceRef={row.citation} />}</span><span className="shrink-0 tabular-nums">{fmt(row.value)}{row.upper !== null ? `–${fmt(row.upper)}` : ''}</span></div>
        <div className="relative h-2 rounded-full bg-muted" aria-hidden>
          <div className={`absolute inset-y-0 left-0 rounded-full ${row.kind === 'own' ? 'bg-primary' : row.kind === 'median' ? 'bg-foreground' : row.kind === 'mean' ? 'border border-dashed border-foreground bg-muted-foreground/40' : 'bg-muted-foreground/55'}`} style={{ width: `${100 * row.value / max}%` }} />
          {row.upper !== null && <div className={`absolute inset-y-0 rounded-r-full border-y border-r ${row.kind === 'own' ? 'border-primary bg-primary/20' : 'border-foreground/50 bg-muted-foreground/20'}`} style={{ left: `${100 * row.value / max}%`, width: `${100 * (row.upper - row.value) / max}%` }} />}
        </div>
      </div>)}
    </div>
    {!c.own && <p className="mt-2 text-xs text-muted-foreground">No sourced value for the reference model.</p>}
    {!c.n && <p className="mt-2 text-xs text-muted-foreground">Median and mean unavailable: no comparable sourced values.</p>}
    {c.median_delta !== null && <p className="mt-3 text-xs">Reference minus competitor median: <strong>{c.median_delta > 0 ? '+' : ''}{fmt(c.median_delta)} {c.unit}</strong></p>}
    {c.delta !== null && <p className="mt-3 text-xs">Reference minus competitor mean: <strong>{c.delta > 0 ? '+' : ''}{fmt(c.delta)} {c.unit}</strong>{c.direction === 'lower' ? '. Lower is favourable.' : c.direction === 'higher' ? '. Higher is favourable for this metric.' : '. Size alone is not a quality rating.'}</p>}
    <details className="mt-3 border-t border-border pt-2"><summary className="cursor-pointer text-xs font-medium focus-visible:outline-2 focus-visible:outline-ring">Validate values and benchmarks</summary>
      <div className="mt-3 space-y-3"><p className="text-xs text-muted-foreground">Median and mean exclude the reference model. Each selected rival contributes once. Interval endpoints are aggregated separately. Incompatible standards and unconfirmed values are excluded.</p>
        {c.observations.map((o) => <SourceFact key={o.id} observation={o} busy={busy} validate={validate} />)}
        {c.excluded.length > 0 && <ul className="space-y-1 text-xs text-muted-foreground">{c.excluded.map((e) => <li key={e.model}>{e.model}: {e.reason}</li>)}</ul>}
      </div>
    </details>
  </article>
}

function FeatureMatrix({ data, comparisons, busy, validate }: { data: Overview; comparisons: Comparison[]; busy: boolean; validate: (mode: 'recrawl' | 'reevaluate', id: string) => void }) {
  const columns = [{ id: data.model.id, name: data.model.name, variant: data.variant }, ...data.rivals.map((r) => ({ id: r.rival_id, name: r.name, variant: r.rival_variant }))]
  return <section className="rounded-2xl border border-border bg-background p-4 shadow-xs"><h3 className="text-base">Features at a glance</h3><p className="mb-3 mt-1 text-xs text-muted-foreground">Documented claims, not quality scores. “No evidence” does not mean a feature is absent. Median and mean apply to measured numbers only.</p><div className="overflow-x-auto"><table className="w-full text-left text-xs"><caption className="sr-only">Source coverage for connectivity, assistance and comfort by model</caption><thead><tr><th scope="col" className="p-2">Section</th>{columns.map((col, i) => <th scope="col" key={col.id} className={`min-w-36 p-2 ${i === 0 ? 'text-primary' : ''}`}>{col.name}<span className="block font-normal">{col.variant}</span></th>)}</tr></thead><tbody>{comparisons.map((c) => <tr key={c.metric} className="border-t border-border"><th scope="row" className="p-2 align-top">{c.section}</th>{columns.map((col, i) => { const facts = c.observations.filter((o) => o.model_id === col.id); return <td key={col.id} className={`p-2 align-top ${i === 0 ? 'bg-primary/5' : ''}`}>{facts.length ? <><span className={`mb-1 block font-medium ${i === 0 ? 'text-primary' : ''}`}>{facts.length} documented {facts.length === 1 ? 'claim' : 'claims'}</span>{facts.slice(0, 2).map((o) => <p key={o.id} className="mb-1">{o.text_value}<CitationChip n="Source" sourceRef={o.citation} /></p>)}{facts.length > 2 && <p className="text-muted-foreground">+{facts.length - 2} in evidence below</p>}</> : <span className="text-muted-foreground">No evidence collected</span>}</td> })}</tr>)}</tbody></table></div>{comparisons.map((c) => <details key={c.metric} className="mt-3 border-t border-border pt-2"><summary className="cursor-pointer text-xs font-medium">Validate {c.section.toLowerCase()} claims ({c.observations.length})</summary><div className="mt-3 space-y-3">{c.observations.map((o) => <SourceFact key={o.id} observation={o} busy={busy} validate={validate} />)}</div></details>)}</section>
}

function Dataset({ data }: { data: Overview }) {
  const [limit, setLimit] = useState(50)
  const total = data.dataset.feedback.reduce((sum, row) => sum + row.n, 0)
  const top = Math.max(...data.dataset.feedback.map((r) => r.n), 1)
  const maxStudy = Math.max(...data.dataset.study.filter((r) => r.metric === 'mean').map((r) => r.value), 1)
  return <div className="space-y-5">
    <section className="rounded-2xl border border-border bg-background p-4 shadow-xs"><h3 className="text-base font-semibold">Customer experience</h3><p className="mb-4 mt-1 text-xs text-muted-foreground">{total} feedback records for this model family and market. Counts describe evidence volume, not satisfaction. The study covers the family, not an individual variant.</p>
      {data.dataset.feedback.length === 0 ? <p className="text-sm text-muted-foreground">No customer feedback for this market in the dataset.</p> : <div className="space-y-3">{data.dataset.feedback.map((row) => <details key={row.section}><summary className="cursor-pointer text-sm"><span className="inline-flex w-[calc(100%-1.25rem)] justify-between gap-2"><span>{row.section || 'Unclassified'}</span><span className="tabular-nums">{row.n}</span></span><span className="mt-1.5 block h-1.5 rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${100 * row.n / top}%` }} /></span></summary><div className="space-y-2 py-3"><p className="text-xs text-muted-foreground">{row.positive} positive, {row.negative} negative, {row.requests} requests. Aggregated by the stored domain label, model family and market.</p>{row.examples.map((example, i) => <p key={i} className="text-xs">{example.comment} <CitationChip n={i + 1} sourceRef={example.citation} /></p>)}</div></details>)}</div>}
    </section>
    <details className="rounded-2xl border border-border bg-background p-4 shadow-xs"><summary className="cursor-pointer font-semibold">All customer-study findings ({data.dataset.study.length})</summary><p className="my-3 text-xs text-muted-foreground">Reported source means and answer shares. Respondent counts and a matching competitor study are unavailable; no market mean is inferred. Bars start at zero and use the largest reported mean in this source as their maximum; shares use 100%.</p><div className="space-y-3">{data.dataset.study.slice(0, limit).map((r) => <div key={r.id} className="space-y-1"><p className="text-xs">{r.question}{r.answer_option ? `, ${r.answer_option}` : ''}: <strong>{fmt(r.metric === 'share' ? r.value * 100 : r.value)}{r.metric === 'share' ? '%' : ' reported mean'}</strong> <CitationChip n="Source" sourceRef={r.citation} /></p><div className="h-1.5 rounded-full bg-muted" aria-hidden><div className="h-full rounded-full bg-primary" style={{ width: `${100 * r.value / (r.metric === 'share' ? 1 : maxStudy)}%` }} /></div></div>)}</div>{limit < data.dataset.study.length && <Button variant="outline" className="mt-3" onClick={() => setLimit((n) => n + 50)}>Show more study findings</Button>}{data.dataset.study.length === 0 && <p className="text-sm text-muted-foreground">No study cells for this model and market.</p>}</details>
    <details className="rounded-2xl border border-border bg-background p-4 shadow-xs"><summary className="cursor-pointer font-semibold">Portfolio and sales evidence</summary><div className="mt-3 space-y-3">{data.dataset.sales.map((r) => <p key={r.id} className="text-sm">{r.year}: {fmt(r.volume)} vehicles{r.is_forecast ? ' (forecast)' : ''} <CitationChip n="Source" sourceRef={r.citation} /></p>)}{data.dataset.sales.length === 0 && <p className="text-sm text-muted-foreground">No matching sales rows.</p>}<a href="#evidence" className="text-xs text-primary underline">Explore the model’s catalog and equipment evidence</a></div></details>
  </div>
}

export function ModelsPage() {
  const [models, setModels] = useState<Model[]>([])
  const [markets, setMarkets] = useState<{ code: string; name: string }[]>([])
  const [selected, setSelected] = useState('')
  const [variant, setVariant] = useState('')
  const [market, setMarket] = useState('EU')
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [manual, setManual] = useState<'model' | 'rival' | null>(null)
  const [name, setName] = useState('')
  const [newVariant, setNewVariant] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [rivalVariant, setRivalVariant] = useState('')
  const [powertrain, setPowertrain] = useState('ICE')
  const [all, setAll] = useState(false)
  const generation = useRef(0)
  const model = models.find((m) => m.id === selected)
  const scopeKey = `${selected}/${variant}/${market}`
  const scopeRef = useRef(scopeKey)
  useEffect(() => { scopeRef.current = scopeKey }, [scopeKey])

  function choose(m: Model) { setSelected(m.id); setVariant(m.variants[0]?.name ?? ''); setAll(false) }
  useEffect(() => {
    const ctrl = new AbortController()
    api.models(ctrl.signal).then((r) => { setModels(r.models); setMarkets(r.markets); setMarket(r.default_market); const fromUrl = new URLSearchParams(window.location.hash.split('?')[1]).get('id'); const initial = r.models.find((m) => m.id === fromUrl) ?? r.models[0]; if (initial) choose(initial); else setLoading(false) }).catch((e) => { if (e.name !== 'AbortError') { setError(message(e)); setLoading(false) } })
    return () => ctrl.abort()
  }, [])
  useEffect(() => {
    if (!selected) return
    const ctrl = new AbortController(); const current = ++generation.current
    setLoading(true); setData(null); setError(null)
    api.modelOverview(selected, variant, market, ctrl.signal).then((result) => { if (current === generation.current) setData(result) }).catch((e) => { if (e.name !== 'AbortError') setError(message(e)) }).finally(() => { if (current === generation.current) setLoading(false) })
    return () => ctrl.abort()
  }, [selected, variant, market])

  async function operation(action: () => Promise<Overview>) {
    if (busy) return
    const key = scopeKey; setBusy(true); setError(null)
    try { const result = await action(); if (scopeRef.current === key) setData(result) }
    catch (e) { setError(message(e)) }
    finally { setBusy(false) }
  }
  const validate = (mode: 'recrawl' | 'reevaluate', id?: string) => void operation(() => api.validateModel(selected, variant, market, mode, id))
  async function add(e: FormEvent) {
    e.preventDefault(); if (!name.trim() || busy) return
    if (manual === 'rival') { setManual(null); await operation(() => api.researchModel(selected, variant, market, name.trim(), sourceUrl.trim() || undefined, rivalVariant.trim() || undefined)); setSourceUrl(''); setRivalVariant(''); return }
    setBusy(true); setError(null)
    try { const m = await api.addModel(name.trim(), newVariant.trim(), newVariant.trim() ? powertrain : null); setModels((list) => [...list.filter((x) => x.id !== m.id), m]); choose(m); setManual(null); setData(null); const result = await api.researchModel(m.id, m.variants[0]?.name ?? '', market); if (scopeRef.current.startsWith(m.id)) setData(result) }
    catch (e) { setError(message(e)) }
    finally { setBusy(false) }
  }
  const numerical = data?.comparisons.filter((c) => c.unit) ?? []
  const qualitative = data?.comparisons.filter((c) => !c.unit) ?? []
  const shown = all ? numerical : numerical.slice(0, 6)

  return <SourceViewerProvider><div className="min-h-0 flex-1 overflow-y-auto bg-canvas-tint" data-testid="models-page"><div className="mx-auto w-full max-w-[1500px] space-y-5 px-4 py-6 sm:px-8">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><h1 className="flex items-center gap-2 text-2xl"><Car className="size-6 text-primary" aria-hidden /> Model comparisons</h1><p className="mt-1 text-sm text-muted-foreground">BMW dataset evidence and sourced competitors, calculated by the comparison API.</p></div><Button variant="outline" disabled={busy} onClick={() => { setManual('model'); setName(''); setNewVariant('') }}><Plus aria-hidden /> Add model</Button></header>
    <div className="grid gap-3 sm:grid-cols-3"><Choice id="comparison-model" label="Model" value={selected} options={models.map((m) => ({ value: m.id, label: m.name }))} onChange={(id) => { const m = models.find((x) => x.id === id); if (m) choose(m) }} disabled={busy} /><Choice id="comparison-variant" label="Variant" value={variant} options={model?.variants.length ? model.variants.map((v) => ({ value: v.name, label: `${v.name} (${v.powertrain ?? 'unknown powertrain'})` })) : [{ value: '', label: 'Family overview; no variant in dataset' }]} onChange={setVariant} disabled={busy} /><Choice id="comparison-market" label="Market" value={market} options={markets.map((m) => ({ value: m.code, label: m.name }))} onChange={setMarket} disabled={busy} /></div>
    {error && <p role="alert" className="rounded-xl border border-destructive/30 bg-background p-3 text-sm text-destructive">{error} <Button variant="ghost" size="sm" onClick={() => { if (selected) void operation(() => api.modelOverview(selected, variant, market)); else window.location.reload() }}>Retry</Button></p>}
    {loading ? <div className="grid gap-4 lg:grid-cols-[1fr_380px]" aria-label="Loading model overview"><div className="grid gap-4 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-48 rounded-2xl" />)}</div><Skeleton className="h-[560px] rounded-2xl" /></div> : !model ? <p className="rounded-xl bg-background p-5">No models are registered. Add a model or load the dataset from Sources.</p> : data && <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-background p-4 shadow-xs"><div><h2 className="text-lg">{model.name}</h2><p className="mt-1 text-xs text-muted-foreground">{model.origin === 'dataset' ? 'Internal dataset model' : 'Manually added web model'}; {model.identity.basis}{model.identity.citation && <CitationChip n="Identity source" sourceRef={model.identity.citation} />}. {data.powertrain ?? 'Powertrain unconfirmed'}.</p><p className="mt-1 text-xs text-muted-foreground">Recalculated <time dateTime={data.computed_at}>{stamp(data.computed_at)}</time>{data.research?.finished_at ? `. Research finished ${stamp(data.research.finished_at)} (${data.research.status}).` : ''}</p></div><div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => void operation(() => api.researchModel(selected, variant, market))}>{busy ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />} {busy ? 'Researching and validating' : data.research ? 'Refresh competitor research' : 'Research competitors'}</Button><Button variant="outline" disabled={busy} onClick={() => validate('reevaluate')}>Reevaluate evidence</Button></div></div>
      {busy && <p role="status" className="text-sm">The server is collecting or reevaluating source evidence. Existing results stay visible; this can take a few minutes.</p>}
      {model.origin === 'dataset' && !model.markets.includes(market) && <p className="rounded-xl border border-border bg-background p-3 text-sm">No customer-study data for this model in the selected market. Supplied study markets: {model.markets.join(', ') || 'none'}. Data from other models or markets is kept separate.</p>}
      {data.research?.notes.length ? <details className="rounded-xl border border-border bg-background p-3"><summary className="cursor-pointer text-sm">Research coverage and validation notes ({data.research.notes.length})</summary><ul className="mt-3 space-y-2 text-xs text-muted-foreground">{data.research.notes.map((n, i) => <li key={i} className="break-words">{n}</li>)}</ul></details> : null}
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,400px)]">
        <div className="min-w-0 space-y-4"><Tabs defaultValue="comparisons"><TabsList variant="line" className="w-full justify-start"><TabsTrigger value="comparisons" className="text-muted-foreground">Market comparison</TabsTrigger><TabsTrigger value="dataset" className="text-muted-foreground">BMW evidence</TabsTrigger></TabsList><TabsContent value="comparisons" className="space-y-4">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs"><span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-primary" aria-hidden /> Reference model</span><span className="flex items-center gap-1.5"><span className="size-2.5 bg-foreground" aria-hidden /> Competitor median</span><span className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-muted-foreground/55" aria-hidden /> Individual competitors</span><span className="flex items-center gap-1.5"><span className="h-2.5 w-4 border border-dashed border-foreground bg-muted-foreground/40" aria-hidden /> Competitor mean</span></div>
          <p className="text-xs text-muted-foreground">Up to six key metrics. Median and mean cover the selected comparable competitors, not the entire market. A shaded extension denotes a reported range.</p>
          {numerical.length ? <div className="grid gap-3 min-[650px]:grid-cols-2">{shown.map((c) => <MetricChart key={c.metric} comparison={c} name={variant || model.name} busy={busy} validate={validate} />)}</div> : <div className="rounded-2xl border border-border bg-background p-5"><h3 className="text-base">Collect the comparison evidence</h3><p className="mt-2 text-sm text-muted-foreground">Run research to discover competitors and read their official sources. Missing values will remain visible as gaps.</p></div>}
          {numerical.length > 6 && <Button variant="outline" onClick={() => setAll((v) => !v)}>{all ? 'Show six key metrics' : `Show all ${numerical.length} metrics`}</Button>}
          <section className="rounded-2xl border border-border bg-background p-4 shadow-xs"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-base">Selected competitors ({data.rivals.length})</h3><Button size="sm" variant="outline" disabled={busy} onClick={() => { setName(''); setManual('rival') }}><Plus aria-hidden /> Add competitor</Button></div><p className="mt-2 text-xs text-muted-foreground">Discovery proposes this cohort from the web. Check the selection rationale and remove unsuitable models before interpreting a mean.</p><ul className="mt-3 space-y-3">{data.rivals.map((r) => <li key={r.id} className="border-t border-border pt-3"><div className="flex items-start justify-between gap-2"><p className="text-sm font-medium">{r.name}, {r.rival_variant}</p><Button size="sm" variant="ghost" disabled={busy} onClick={() => void operation(() => api.removeRival(selected, r.id, variant, market))}>Remove</Button></div><p className="text-xs text-muted-foreground">{r.reason} Selection: {r.selection}.</p>{r.discovery_url && <a href={r.discovery_url} target="_blank" rel="noreferrer noopener" className="text-xs text-primary underline">Discovery source</a>}<p className="text-xs text-muted-foreground">{r.observations.length} sourced observations{!r.observations.length ? '; no validated numeric contribution yet' : ''}.</p>{r.sources?.map((source) => <p key={source.file} className="mt-1 text-xs text-muted-foreground"><a href={source.file} target="_blank" rel="noreferrer noopener" className="text-primary underline">Stored source</a>: crawled <time dateTime={source.retrieved_at}>{stamp(source.retrieved_at)}</time>, {source.passages} passages.</p>)}<div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={busy || !r.discovery_url} onClick={() => void operation(() => api.validateModel(selected, variant, market, 'recrawl', undefined, r.id))}>Crawl rival sources</Button><Button size="sm" variant="ghost" disabled={busy || (!r.sources?.length && !r.observations.length)} onClick={() => void operation(() => api.validateModel(selected, variant, market, 'reevaluate', undefined, r.id))}>Reevaluate rival</Button></div></li>)}</ul></section>
          {qualitative.length > 0 && <FeatureMatrix data={data} comparisons={qualitative} busy={busy} validate={validate} />}
          <details className="rounded-xl bg-background p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium">Median, mean and data boundaries</summary><p className="mt-2">{data.mean_method}</p><p className="mt-2">Specifications and web claims are extracted evidence, ready for human validation. Internal feedback counts and customer-study scores are not pooled with specification values or web review ratings. Every refresh saves a new source snapshot; previous citations stay available.</p></details>
        </TabsContent><TabsContent value="dataset"><Dataset key={`${selected}/${market}`} data={data} /></TabsContent></Tabs></div>
        <aside aria-label="Model research chat" className="flex h-[680px] min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-xs xl:sticky xl:top-0"><LiveResearch key={scopeKey} modelScope={{ comparison_model_id: selected, comparison_variant: variant, comparison_market: market as 'EU', name: model.name, conversation_id: data.conversation_id, rival_count: data.rivals.length }} /></aside>
      </div>
    </>}
    <Dialog open={manual !== null} onOpenChange={(open) => { if (!open) setManual(null) }}><DialogContent className="max-h-[90dvh] overflow-y-auto"><DialogTitle>{manual === 'rival' ? 'Add competitor' : 'Add model'}</DialogTitle><DialogDescription>{manual === 'rival' ? 'Enter the full make, model and variant. The server will search official sources and validate comparable data.' : 'Add a model beyond the dataset and research its official web evidence.'}</DialogDescription><form onSubmit={add} className="space-y-4"><div className="space-y-1.5"><Label htmlFor="manual-model-name">Make and model{manual === 'rival' ? ', including variant' : ''}</Label><Input id="manual-model-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={160} required minLength={2} /></div>{manual === 'rival' && <details className="space-y-3"><summary className="cursor-pointer text-sm">Use a specific official source (optional)</summary><p className="text-xs text-muted-foreground">Provide a public technical page or PDF when search finds an unsuitable page. Values still have to match the exact variant and source quotations.</p><div className="space-y-1.5"><Label htmlFor="manual-rival-variant">Exact variant in this source</Label><Input id="manual-rival-variant" value={rivalVariant} onChange={(e) => setRivalVariant(e.target.value)} maxLength={120} required={!!sourceUrl} /></div><div className="space-y-1.5"><Label htmlFor="manual-source-url">Official source URL</Label><Input id="manual-source-url" type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} maxLength={2000} /></div></details>}{manual === 'model' && <><div className="space-y-1.5"><Label htmlFor="manual-variant">Variant (optional)</Label><Input id="manual-variant" value={newVariant} onChange={(e) => setNewVariant(e.target.value)} maxLength={120} /></div><Choice id="manual-powertrain" label="Powertrain" value={powertrain} options={[{ value: 'ICE', label: 'Combustion or mild hybrid' }, { value: 'PHEV', label: 'Plug-in hybrid' }, { value: 'BEV', label: 'Battery electric' }]} onChange={setPowertrain} /></>}<Button type="submit" disabled={busy || name.trim().length < 2}>{busy ? 'Searching' : 'Add and research'}</Button></form></DialogContent></Dialog>
  </div></div></SourceViewerProvider>
}
