import { Button } from '@/components/ui/button'
import { useSourceViewer } from '@/features/sources/SourceViewer'
import type { MarketSignal, MarketWebAssessmentResponse, MarketWebEvidence } from '@/types/api'

type State = 'idle' | 'loading' | 'error' | 'ready'
type Props = {
  marketLabel: string
  internal?: MarketSignal
  web?: MarketWebAssessmentResponse['markets'][number]
  direction?: MarketSignal['direction']
  internalState: State
  webState: State
  context: MarketWebEvidence[]
}
const labels = { positive: 'Benefit signal', negative: 'Risk signal', mixed: 'Benefits and risks', insufficient: 'No directional evidence' }
const conclusions = {
  positive: 'Available evidence suggests a benefit or unmet demand for this feature.',
  negative: 'Available evidence identifies an acceptance, cost, quality, or usability risk.',
  mixed: 'Evidence contains both benefits and risks. Review the trade-offs before choosing the feature.',
  insufficient: 'The available evidence does not establish a direction. This does not mean the feature has no effect.',
}
const waiting = (state: State) => state === 'loading' ? 'Research in progress' : state === 'error' ? 'Unavailable, retry above' : 'Awaiting assessment'
const stanceLabel = { supports: 'Benefit or demand', risk: 'Risk', mixed: 'Benefit and risk', unclear: 'Unclear', context: 'Context only' }

function PublicSources({ evidence }: { evidence: MarketWebEvidence[] }) {
  return <ul className="mt-4 space-y-5">{evidence.map((e) => <li key={e.url} className="border-l-2 border-border pl-4 text-sm">
    <p className="mb-1 text-xs font-semibold text-muted-foreground">{stanceLabel[e.stance]}</p>
    <a href={e.url} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">{e.title}</a>
    <blockquote className="mt-2 leading-relaxed">{e.summary}</blockquote>
    <p className="mt-2 text-xs text-muted-foreground">{e.reason}</p>
    <p className="mt-2 text-xs text-muted-foreground">{e.source_type}, {e.scope}. Retrieved {new Date(e.retrieved_at).toLocaleDateString('en-GB')}.</p>
  </li>)}</ul>
}

export function EvidencePanel({ marketLabel, internal, web, direction, internalState, webState, context }: Props) {
  const openSource = useSourceViewer()
  const counts = internal?.signal_counts ?? {
    benefit: internal?.evidence.filter((e) => e.stance === 'supports' || e.stance === 'mixed').length ?? 0,
    risk: internal?.evidence.filter((e) => e.stance === 'risk' || e.stance === 'mixed').length ?? 0,
    unclear: internal?.evidence.filter((e) => e.stance === 'unclear').length ?? 0,
  }
  return <section aria-label={`${marketLabel} evidence`} className="border-t border-border px-6 py-6">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div><h3 className="text-lg">{marketLabel} evidence</h3><p className="mt-1 text-sm text-muted-foreground">Why this feature receives its market signal.</p></div>
      <p className="text-sm font-semibold">{direction ? labels[direction] : internalState === 'loading' || webState === 'loading' ? 'Checking evidence' : 'Awaiting assessment'}</p>
    </div>
    {direction && <p className="mt-4 text-sm leading-relaxed">{conclusions[direction]}{(internalState === 'loading' || webState === 'loading') && ' This signal may change as the remaining evidence arrives.'}{(internalState === 'error' || webState === 'error' || web?.status === 'partial') && ' Coverage is incomplete.'}</p>}
    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <div className="min-w-0 rounded-xl bg-canvas-tint p-5">
        <h4 className="text-sm">Internal customer feedback</h4>
        <p className="mt-2 text-sm font-semibold">{internal ? labels[internal.direction] : waiting(internalState)}</p>
        {internal && <>
          <p className="mt-2 text-sm text-muted-foreground">{internal.explanation}</p>
          <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
            {([['Benefit / demand', counts.benefit], ['Risk', counts.risk], ['Unclear', counts.unclear]] as const).map(([label, count]) => <div key={label}><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{count}</dd></div>)}
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">Reviewed {internal.reviewed} of {internal.matched_total} distinct matching comments. Total feedback loaded in this market: {internal.total_feedback}.</p>
          {internal.evidence.some((e) => e.stance === 'mixed') && <p className="mt-2 text-xs text-muted-foreground">A comment with both benefit and risk contributes to both counts.</p>}
          {internal.evidence.length > 0 && <details className="mt-4"><summary className="cursor-pointer rounded-lg py-2 text-sm text-primary focus-visible:outline-2 focus-visible:outline-ring">View {internal.evidence.length} sample {internal.evidence.length === 1 ? 'comment' : 'comments'}</summary>
            <ul className="mt-3 space-y-4">{internal.evidence.map((e, i) => <li key={e.citation.id} className="border-l-2 border-border pl-3">
              <p className="text-xs font-semibold text-muted-foreground">{stanceLabel[e.stance]}</p>
              <blockquote className="mt-1 text-sm leading-relaxed">{e.citation.quote}</blockquote>
              <p className="mt-2 text-xs text-muted-foreground">{e.reason}</p>
              <Button variant="link" className="px-0 text-xs" aria-label={`View feedback source ${i + 1}`} onClick={() => openSource(e.citation)}>View source {i + 1}</Button>
            </li>)}</ul>
          </details>}
        </>}
      </div>
      <div className="min-w-0 rounded-xl bg-canvas-tint p-5">
        <h4 className="text-sm">Public web evidence</h4>
        <p className="mt-2 text-sm font-semibold">{web ? labels[web.direction] : waiting(webState)}</p>
        {web && <>
          <p className="mt-2 text-sm text-muted-foreground">{web.explanation || (web.evidence.length ? 'Verified public excerpts relevant to this feature and market.' : 'No relevant cited public evidence was returned for this market.')}</p>
          <PublicSources evidence={web.evidence} />
        </>}
      </div>
    </div>
    {context.length > 0 && <details className="mt-5 border-t border-border pt-3"><summary className="cursor-pointer rounded-lg py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">General web context ({context.length})</summary>
      <p className="mt-2 text-sm text-muted-foreground">Verified feature mentions without an established market direction. These do not change map colors.</p><PublicSources evidence={context} />
    </details>}
    <details className="mt-5 border-t border-border pt-3"><summary className="cursor-pointer rounded-lg py-2 text-sm text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring">How to read this evidence</summary>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">The backend matches feature names and known functional synonyms, deduplicates comments, and interprets up to 12 internal passages per market using conservative local language rules. The sample is not a representative survey. A missing feature can indicate demand; complaints about operation can indicate implementation risk. Ambiguous wording remains unclear.</p>
      <p className="mt-3 text-sm leading-relaxed text-muted-foreground">Public source relevance and stance are model interpretations checked against fetched page excerpts and geographic context. Manufacturer availability and general context do not establish impact. Benefits and risks from either source remain visible as trade-offs. A country review does not establish a region-wide or BMW-specific share effect. Numeric share changes are your scenario assumptions.</p>
    </details>
  </section>
}
