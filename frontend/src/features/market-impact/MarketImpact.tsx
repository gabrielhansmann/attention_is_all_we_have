import { useEffect, useRef, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Download, Globe2, Minus, RotateCcw } from 'lucide-react'
import { PageShell } from '@/components/layout/PageShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { SourceViewerProvider, useSourceViewer } from '@/features/sources/SourceViewer'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Hit, Line, Market, MarketOptionsResponse, MarketAssessmentRequest, MarketAssessmentResponse, MarketWebAssessmentResponse } from '@/types/api'
import { assessedImpact, combineDirections, changeLabel, emptyScenario, IMPACT_COLORS, MARKETS, shareLabel, type Assumption, type Impact, type Scenario } from './scenario'
import { WorldMap } from './WorldMap'

type Catalog = { line: Line; state: 'loading' } | { line: Line; state: 'error'; message: string } | { line: Line; state: 'ready'; data: MarketOptionsResponse }
const LINES: Line[] = ['F70', 'G60', 'G68', 'G70']
const STATE_LABEL: Record<Impact['state'], string> = { positive: 'Benefit', negative: 'Risk', mixed: 'Trade-offs', neutral: 'No change', unknown: 'Unknown' }
const SIGNAL_LABEL: Record<Impact['state'], string> = { positive: 'Benefit signal', negative: 'Risk signal', mixed: 'Benefits and risks', neutral: 'No change', unknown: 'No matched evidence' }
type Load<T> = { key: string; state: 'idle' | 'loading' } | { key: string; state: 'error'; message: string } | { key: string; state: 'ready'; data: T }
type Assessment = Load<MarketAssessmentResponse>
type AssessmentTarget = { key: string; body: MarketAssessmentRequest }
const commentCount = (count: number) => `${count} matching ${count === 1 ? 'comment' : 'comments'}`

function Choice({ label, value, items, onChange }: { label: string; value: string; items: { value: string; label: string }[]; onChange: (value: string) => void }) {
  const id = label === 'Vehicle line' ? 'impact-line' : 'impact-feature'
  return <div className="min-w-0 space-y-2">
    <Label htmlFor={id}>{label}</Label>
    <Select items={items} value={value || null} onValueChange={(v) => { if (v !== null) onChange(v) }}>
      <SelectTrigger id={id}><SelectValue placeholder="Choose an optional feature" /></SelectTrigger>
      <SelectContent>{items.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
    </Select>
  </div>
}

function Content() {
  const openSource = useSourceViewer()
  const [line, setLine] = useState<Line>('G60')
  const [catalog, setCatalog] = useState<Catalog>({ line: 'G60', state: 'loading' })
  const [retry, setRetry] = useState(0)
  const [featureId, setFeatureId] = useState('')
  const [custom, setCustom] = useState('')
  const [market, setMarket] = useState<Market>('US')
  const [included, setIncluded] = useState(true)
  const [scenarios, setScenarios] = useState<Record<string, Scenario>>({})
  const [assessment, setAssessment] = useState<Assessment>({ key: '', state: 'idle' })
  const [assessmentTarget, setAssessmentTarget] = useState<AssessmentTarget | null>(null)
  const [webAssessment, setWebAssessment] = useState<Load<MarketWebAssessmentResponse>>({ key: '', state: 'idle' })
  const webCache = useRef(new Map<string, MarketWebAssessmentResponse>())
  const assessmentCache = useRef(new Map<string, MarketAssessmentResponse>())

  useEffect(() => {
    const controller = new AbortController()
    api.marketOptions(line, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setCatalog({ line, state: 'ready', data }) })
      .catch((e: unknown) => { if (!controller.signal.aborted) setCatalog({ line, state: 'error', message: e instanceof Error ? e.message : 'Could not load optional equipment.' }) })
    return () => controller.abort()
  }, [line, retry])

  useEffect(() => {
    if (!assessmentTarget) return
    const controller = new AbortController()
    if (!assessmentCache.current.has(assessmentTarget.key)) api.marketAssessment(assessmentTarget.body, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        assessmentCache.current.set(assessmentTarget.key, data)
        setAssessment({ key: assessmentTarget.key, state: 'ready', data })
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setAssessment({ key: assessmentTarget.key, state: 'error', message: e instanceof Error ? e.message : 'Could not assess this feature.' })
      })
    if (!webCache.current.has(assessmentTarget.key)) api.marketWebAssessment(assessmentTarget.body, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        webCache.current.set(assessmentTarget.key, data)
        setWebAssessment({ key: assessmentTarget.key, state: 'ready', data })
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setWebAssessment({ key: assessmentTarget.key, state: 'error', message: e instanceof Error ? e.message : 'Could not research public sources.' })
      })
    return () => controller.abort()
  }, [assessmentTarget])

  const options = catalog.line === line && catalog.state === 'ready' ? catalog.data.options : []
  const option: Hit | undefined = options.find((o) => o.citation.id === featureId)
  const name = featureId === 'custom' ? custom.trim() : option?.text ?? ''
  const ready = !!name
  const scenarioKey = `${line}:${featureId === 'custom' ? `custom:${name}` : featureId}`
  const scenario = scenarios[scenarioKey] ?? emptyScenario()
  const activeAssessment = assessment.key === scenarioKey ? assessment : undefined
  const activeWeb = webAssessment.key === scenarioKey ? webAssessment : undefined
  const webSignals = activeWeb?.state === 'ready' ? activeWeb.data.markets : []
  const signals = activeAssessment?.state === 'ready' ? activeAssessment.data.markets.map((s) => ({ ...s, direction: combineDirections(s.direction, webSignals.find((w) => w.market === s.market)?.direction) })) : []
  const webSignal = webSignals.find((s) => s.market === market)
  const signal = signals.find((s) => s.market === market)
  const internalSignal = activeAssessment?.state === 'ready' ? activeAssessment.data.markets.find((s) => s.market === market) : undefined
  const impacts = Object.fromEntries(MARKETS.map(({ key }) => [key, assessedImpact(ready ? scenario[key] : { baseline: '', delta: '', reason: '' }, ready ? included : true, ready ? signals.find((s) => s.market === key) : undefined)])) as Record<Market, Impact>
  const selected = impacts[market]
  const current = scenario[market]
  const selectedMarket = MARKETS.find((m) => m.key === market)!
  const invalid = MARKETS.some(({ key }) => impacts[key].error)

  const startAssessment = (key: string, body: MarketAssessmentRequest, refresh = false) => {
    if (refresh) { assessmentCache.current.delete(key); webCache.current.delete(key) }
    const cached = assessmentCache.current.get(key)
    const cachedWeb = webCache.current.get(key)
    setWebAssessment(cachedWeb ? { key, state: 'ready', data: cachedWeb } : { key, state: 'loading' })
    setAssessment(cached ? { key, state: 'ready', data: cached } : { key, state: 'loading' })
    setAssessmentTarget(cached && cachedWeb ? null : { key, body })
  }
  const assessSelected = () => startAssessment(scenarioKey, featureId === 'custom' ? { line, feature: name } : { line, option_id: featureId }, true)

  const update = (field: keyof Assumption, value: string) => setScenarios((prev) => ({ ...prev,
    [scenarioKey]: { ...(prev[scenarioKey] ?? emptyScenario()), [market]: { ...(prev[scenarioKey]?.[market] ?? { baseline: '', delta: '', reason: '' }), [field]: value } },
  }))

  const exportScenario = () => {
    const report = {
      kind: 'market-share-scenario', basis: 'Evidence-based directions and user-entered share assumptions, not a validated forecast', vehicle_line: line,
      feature: name, feature_included: included, catalog_citation: option?.citation ?? null,
      geography: 'Schematic business regions: Europe excluding Russia, China, United States, rest of world',
      markets: MARKETS.map(({ key, label }) => ({ market: key, label, assumptions: scenario[key], result: impacts[key] })),
      assessment: activeAssessment?.state === 'ready' ? activeAssessment.data : null,
      public_research: activeWeb?.state === 'ready' ? activeWeb.data : null,
    }
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = `market-impact-${line}.json`; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <PageShell title="Market impact" description="Choose an optional feature to assess customer support across markets." Icon={Globe2} testId="market-impact">
    <section aria-label="Feature selection" className="rounded-2xl border border-border bg-background p-6 shadow-xs">
      <div className="grid gap-5 sm:grid-cols-[8rem_minmax(0,1fr)]">
        <Choice label="Vehicle line" value={line} items={LINES.map((value) => ({ value, label: value }))}
          onChange={(value) => { setLine(value as Line); setCatalog({ line: value as Line, state: 'loading' }); setFeatureId(''); setIncluded(true); setAssessmentTarget(null); setAssessment({ key: '', state: 'idle' }); setWebAssessment({ key: '', state: 'idle' }) }} />
        <Choice label="Optional feature" value={featureId} items={[...options.map((o) => ({ value: o.citation.id, label: `${o.meta.code ? `${o.meta.code} · ` : ''}${o.text}` })), { value: 'custom', label: 'Custom optional feature' }]}
          onChange={(value) => {
            setFeatureId(value); setIncluded(true)
            if (value === 'custom') { setAssessmentTarget(null); setAssessment({ key: '', state: 'idle' }); setWebAssessment({ key: '', state: 'idle' }) }
            else startAssessment(`${line}:${value}`, { line, option_id: value })
          }} />
      </div>
      {catalog.state === 'loading' && <div className="mt-4 flex items-center gap-3" role="status"><Skeleton className="h-4 w-32" /><span className="text-xs text-muted-foreground">Loading optional equipment...</span></div>}
      {catalog.state === 'error' && <div className="mt-4 flex flex-wrap items-center gap-3"><p role="alert" className="text-sm text-destructive">{catalog.message} You can use a custom feature.</p><Button variant="outline" onClick={() => { setCatalog({ line, state: 'loading' }); setRetry((n) => n + 1) }}>Retry catalog</Button></div>}
      {catalog.state === 'ready' && catalog.data.options.length === 0 && <p className="mt-4 text-sm text-muted-foreground">No optional equipment is loaded for {line}. Choose a custom feature to explore a scenario.</p>}
      {catalog.state === 'ready' && catalog.data.truncated && <p className="mt-4 text-xs text-muted-foreground">Showing the first 200 catalog options. Use a custom feature for other equipment.</p>}
      {featureId === 'custom' && <div className="mt-4 space-y-2"><Label htmlFor="custom-feature">Feature name</Label><div className="flex flex-wrap gap-2"><Input id="custom-feature" value={custom} maxLength={120} onChange={(e) => { setCustom(e.target.value); setAssessmentTarget(null); setAssessment({ key: '', state: 'idle' }); setWebAssessment({ key: '', state: 'idle' }) }} placeholder="Name the optional feature" className="min-w-0 flex-1 basis-48" /><Button disabled={name.length < 2 || activeAssessment?.state === 'loading'} onClick={assessSelected}>Assess feature</Button></div><p className="text-xs text-muted-foreground">Search internal feedback and public web sources using this name. No catalog evidence is attached.</p></div>}
      {option && <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1"><p className="text-sm text-muted-foreground">Optional on at least one catalog variant. Catalog availability does not establish market impact.</p><Button variant="link" className="px-0" onClick={() => openSource(option.citation)}>View catalog source</Button></div>}
    </section>

    <section aria-label="Market-share scenario" className="overflow-hidden rounded-2xl border border-border bg-background shadow-xs">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border px-6 py-5">
        <div className="min-w-0"><h2 className="break-words text-lg">{ready ? name : 'Choose a feature to begin'}</h2><p className="mt-1 text-sm text-muted-foreground">Green indicates a potential benefit, red an implementation or acceptance risk. Market share is not predicted.</p></div>
        <div className="flex h-11 items-center gap-3"><Label htmlFor="include-feature" className={cn(!ready && 'text-muted-foreground')}>Include feature</Label><Switch id="include-feature" checked={included} disabled={!ready} onCheckedChange={setIncluded} /></div>
      </header>
      {ready && activeAssessment?.state === 'loading' && <div role="status" className="flex items-center gap-3 border-b border-border px-6 py-4"><Skeleton className="h-4 w-20 shrink-0" /><p className="text-sm text-muted-foreground">Assessing customer feedback across markets...</p></div>}
      {ready && activeAssessment?.state === 'error' && <div className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-4"><p role="alert" className="text-sm text-destructive">{activeAssessment.message}</p><Button variant="outline" onClick={assessSelected}>Retry assessment</Button></div>}
      {ready && activeAssessment?.state === 'ready' && <p className="border-b border-border px-6 py-3 text-xs text-muted-foreground">Assessment complete. {signals.reduce((n, s) => n + s.matched_total, 0)} distinct matching comments found across {signals.filter((s) => s.matched_total > 0).length} markets. Entering a share change overrides that market's map color.</p>}
      {ready && activeWeb?.state === 'loading' && <p role="status" className="border-b border-border px-6 py-3 text-xs text-muted-foreground">Researching public web sources. Internal feedback appears independently...</p>}
      {ready && activeWeb?.state === 'error' && <div className="flex flex-wrap items-center gap-3 border-b border-border px-6 py-3"><p role="alert" className="text-xs text-destructive">{activeWeb.message}</p><Button variant="outline" onClick={assessSelected}>Retry research</Button></div>}
      {ready && activeWeb?.state === 'ready' && <p className="border-b border-border px-6 py-3 text-xs text-muted-foreground">{activeWeb.data.public_query ? `Public research complete for ${activeWeb.data.public_query}. Sources below contain verified page excerpts; availability alone does not affect map colors.` : 'No public feature term is mapped for this catalog entry. Use a custom public feature name to research it.'}</p>}
      <div className="grid xl:grid-cols-[minmax(0,1fr)_17rem]">
        <div className="min-w-0 px-4 pt-5 pb-6 sm:px-6">
          <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground" aria-label="Map legend">
            {(['positive', 'negative', 'mixed', 'neutral', 'unknown'] as const).map((state) => <span key={state} className="flex items-center gap-1.5"><span aria-hidden style={{ backgroundColor: IMPACT_COLORS[state], opacity: state === 'neutral' ? 0.55 : 1 }} className={cn('size-2.5 rounded-full', state === 'unknown' && 'border border-muted-foreground')} />{STATE_LABEL[state]}</span>)}
          </div>
          <div className="mt-4 rounded-xl bg-canvas-tint py-3"><WorldMap impacts={impacts} onSelect={setMarket} /></div>
          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Choose a market">
            {MARKETS.map(({ key, label }) => {
              const result = impacts[key]
              const Icon = result.state === 'positive' ? ArrowUpRight : result.state === 'negative' ? ArrowDownRight : Minus
              return <button type="button" key={key} aria-pressed={market === key} onClick={() => setMarket(key)}
                className={cn('min-w-0 rounded-xl border px-3 py-3 text-left focus-visible:outline-2 focus-visible:outline-ring', market === key ? 'border-primary bg-accent' : 'border-border hover:bg-muted')}>
                <span className="block text-xs text-muted-foreground">{label}</span><span className="mt-2 flex items-start gap-1 text-sm font-semibold tabular-nums"><Icon aria-hidden className="mt-0.5 size-4 shrink-0" />{result.basis === 'evidence' ? SIGNAL_LABEL[result.state] : changeLabel(result.delta)}</span>
                <span className="mt-1 block text-xs text-muted-foreground">{result.basis === 'evidence' ? commentCount(signals.find((s) => s.market === key)?.matched_total ?? 0) : STATE_LABEL[result.state]}</span>
              </button>
            })}
          </div>
          <p className="mt-4 text-xs leading-relaxed text-muted-foreground">Select a market to see evidence or enter a share scenario. Countries share their region's value: Europe (excluding Russia), China, United States, and rest of world. Geometry: <a href="https://www.naturalearthdata.com/" target="_blank" rel="noreferrer" className="underline underline-offset-2">Natural Earth</a>.</p>
        </div>
        <section aria-label={`${selectedMarket.label} assumptions`} className="border-t border-border bg-canvas-tint p-6 xl:border-t-0 xl:border-l">
          <h3 className="text-base">{selectedMarket.label}</h3>
          <p className="mt-1 text-xs text-muted-foreground">{included ? 'With the optional feature' : 'Without the optional feature'}</p>
          {signal && <div className="mt-4 border-b border-border pb-4">
            <h4 className="text-sm">Combined evidence signal</h4><p className="mt-1 text-sm font-semibold">{SIGNAL_LABEL[signal.direction === 'insufficient' ? 'unknown' : signal.direction]}</p>
            <p className="mt-2 text-xs text-muted-foreground">Internal: {internalSignal ? SIGNAL_LABEL[internalSignal.direction === 'insufficient' ? 'unknown' : internalSignal.direction] : 'Unavailable'}. Public: {webSignal ? SIGNAL_LABEL[webSignal.direction === 'insufficient' ? 'unknown' : webSignal.direction] : activeWeb?.state === 'loading' ? 'Researching' : 'Unavailable'}.</p>
            <p className="mt-2 text-xs text-muted-foreground">{signal.explanation}</p>
            {signal.evidence.length > 0 && <details className="mt-2"><summary className="min-h-9 cursor-pointer rounded-lg py-2 text-xs text-primary focus-visible:outline-2 focus-visible:outline-ring">View {signal.evidence.length} sample {signal.evidence.length === 1 ? 'comment' : 'comments'}</summary><ul className="max-h-64 space-y-3 overflow-y-auto pt-2">{signal.evidence.map((e, i) => <li key={e.citation.id} className="border-l-2 border-border pl-3"><blockquote className="text-xs">{e.citation.quote}</blockquote><p className="mt-1 text-xs text-muted-foreground">{e.reason}</p><Button variant="link" className="px-0 text-xs" aria-label={`View feedback source ${i + 1}`} onClick={() => openSource(e.citation)}>View source {i + 1}</Button></li>)}</ul></details>}
            <p className="mt-2 text-xs text-muted-foreground">Based on {signal.reviewed} distinct internal sample comments, interpreted locally from feature-specific passages. Matches can refer to the feature's broader function. A missing feature can indicate demand; complaints about its operation indicate implementation risk. Comment counts do not estimate market share.</p>
          </div>}
          {webSignal && <div className="mt-4 border-b border-border pb-4"><h4 className="text-sm">Public web evidence</h4>
            {webSignal.evidence.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">No relevant cited public evidence was returned for this market.</p> : <ul className="mt-2 max-h-80 space-y-4 overflow-y-auto">{webSignal.evidence.map((e) => <li key={e.url} className="space-y-1 text-xs"><a href={e.url} target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-2">{e.title}</a><p className="text-muted-foreground">{e.source_type}, {e.scope}. Retrieved {new Date(e.retrieved_at).toLocaleDateString('en-GB')}.</p><p>{e.summary}</p><p className="text-muted-foreground">{e.reason}</p></li>)}</ul>}
            <p className="mt-2 text-xs text-muted-foreground">Source relevance and stance are model interpretations of verified page excerpts. Broader-market reviews do not establish a BMW-specific share effect. Conflicting signals remain visible as trade-offs.</p></div>}
          {activeWeb?.state === 'ready' && !!activeWeb.data.context?.length && <details className="mt-4 border-b border-border pb-4"><summary className="cursor-pointer py-2 text-sm font-semibold">General web context ({activeWeb.data.context.length})</summary><p className="mt-1 text-xs text-muted-foreground">These verified feature mentions have no established market direction and do not change map colors.</p><ul className="mt-3 max-h-64 space-y-4 overflow-y-auto">{activeWeb.data.context.map((e) => <li key={e.url} className="space-y-1 text-xs"><a href={e.url} target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-2">{e.title}</a><blockquote>{e.summary}</blockquote><p className="text-muted-foreground">{e.scope}. Retrieved {new Date(e.retrieved_at).toLocaleDateString('en-GB')}.</p></li>)}</ul></details>}
          {ready && !signal && activeAssessment?.state !== 'loading' && activeAssessment?.state !== 'error' && <p className="mt-4 text-xs text-muted-foreground">Choose a catalog feature or assess a custom feature to load market evidence.</p>}
          <p className="mt-5 text-sm font-semibold">Share scenario (optional)</p>
          <fieldset disabled={!ready} className="mt-5 space-y-5">
            <div className="space-y-2"><Label htmlFor="baseline-share">Baseline share (%)</Label><Input id="baseline-share" inputMode="decimal" value={ready ? current.baseline : ''} onChange={(e) => update('baseline', e.target.value)} placeholder="Unknown" aria-describedby="baseline-help impact-error" aria-invalid={!!selected.error} /><p id="baseline-help" className="text-xs text-muted-foreground">Optional. Share without this feature.</p></div>
            <div className="space-y-2"><Label htmlFor="assumed-change">Assumed change (pp)</Label><Input id="assumed-change" inputMode="decimal" disabled={!included} value={ready ? current.delta : ''} onChange={(e) => update('delta', e.target.value)} placeholder="e.g. +0.5 or -0.2" aria-describedby="delta-help impact-error" aria-invalid={!!selected.error} /><p id="delta-help" className="text-xs text-muted-foreground">Percentage points. Leave blank to use the evidence signal.</p></div>
            <div className="space-y-2"><Label htmlFor="impact-reason">Reason or source</Label><Textarea id="impact-reason" value={ready ? current.reason : ''} onChange={(e) => update('reason', e.target.value)} maxLength={2000} placeholder="What supports this assumption?" className="min-h-20 bg-background" /></div>
          </fieldset>
          <p id="impact-error" role={selected.error ? 'alert' : undefined} className="mt-3 text-sm text-destructive">{selected.error}</p>
          <div className="mt-5 border-t border-border pt-5" aria-live="polite"><p className="text-xs text-muted-foreground">Scenario share</p>{selected.resulting !== null && <p className="mt-1 text-3xl font-semibold tabular-nums">{shareLabel(selected.resulting)}</p>}<p className="mt-2 text-xs text-muted-foreground">{selected.resulting === null ? 'Add a baseline and assumed change to calculate a numeric share scenario.' : `${shareLabel(selected.baseline)} baseline, ${changeLabel(selected.delta)} feature effect.`}</p></div>
        </section>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-4"><p className="text-xs text-muted-foreground">Assumptions stay in this view. Export to keep a copy.</p><div className="flex flex-wrap gap-2"><Button variant="ghost" disabled={!ready} onClick={() => setScenarios((prev) => ({ ...prev, [scenarioKey]: emptyScenario() }))}><RotateCcw aria-hidden />Reset scenario</Button><Button variant="outline" disabled={!ready || invalid} onClick={exportScenario}><Download aria-hidden />Export scenario</Button></div></footer>
    </section>
  </PageShell>
}

export function MarketImpact() {
  return <SourceViewerProvider><Content /></SourceViewerProvider>
}
