import { useMemo, useState } from 'react'
import { RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import type { Requirement } from '@/types/api'
import { TIER_HELP, pct, tierFor } from './shared'

type Weights = { customer_relevance: number; business_signal: number; strategic_fit: number; effort_proxy: number }
const DEFAULTS: Weights = { customer_relevance: 0.4, business_signal: 0.25, strategic_fit: 0.15, effort_proxy: 0.2 }
const LABELS: { key: keyof Weights; label: string; help: string }[] = [
  { key: 'customer_relevance', label: 'Customer', help: 'What customers ask for' },
  { key: 'business_signal', label: 'Business', help: 'Sales and competitor signal' },
  { key: 'strategic_fit', label: 'Strategic fit', help: 'Fit with the strategy themes' },
  { key: 'effort_proxy', label: 'Effort (subtracts)', help: 'Rough effort, lowers the score' },
]

const composite = (s: NonNullable<Requirement['score']>, w: Weights) =>
  w.customer_relevance * s.customer_relevance + w.business_signal * s.business_signal + w.strategic_fit * s.strategic_fit - w.effort_proxy * s.effort_proxy

/** Customer need against business signal: the two lanes of the prioritization step, one dot per requirement. */
function PriorityMap({ rows }: { rows: { req: Requirement; rank: number }[] }) {
  return (
    <figure className="flex flex-col gap-2">
      <div className="relative h-72 rounded-2xl border border-border bg-card" role="img" aria-label="Map of customer need against business signal. The same data is in the ranked list.">
        <span className="absolute inset-x-0 top-1/2 border-t border-dashed border-border" aria-hidden />
        <span className="absolute inset-y-0 left-1/2 border-l border-dashed border-border" aria-hidden />
        <span className="absolute bottom-2 left-3 text-xs text-muted-foreground">Later</span>
        <span className="absolute right-3 top-2 text-xs font-medium text-accent-foreground">Do first</span>
        {rows.map(({ req, rank }) => (
          <span key={req.id} title={`${req.title}: customer ${pct(req.score!.customer_relevance)}, business ${pct(req.score!.business_signal)}`}
            style={{ left: `${Math.min(96, Math.max(4, req.score!.business_signal * 100))}%`, bottom: `${Math.min(92, Math.max(8, req.score!.customer_relevance * 100))}%` }}
            className="absolute grid size-7 -translate-x-1/2 translate-y-1/2 place-items-center rounded-full bg-primary text-xs font-semibold text-primary-foreground shadow-sm">{rank}</span>
        ))}
      </div>
      <figcaption className="flex justify-between text-xs text-muted-foreground"><span>Customer need (up)</span><span>Business signal (right)</span></figcaption>
    </figure>
  )
}

export function PrioritiesView({ requirements }: { requirements: Requirement[] }) {
  const [w, setW] = useState<Weights>(DEFAULTS)
  const live = requirements.filter((r) => r.status !== 'rejected' && r.status !== 'superseded')
  const scored = live.filter((r) => r.score)
  const unscored = live.filter((r) => !r.score)
  const changed = LABELS.some(({ key }) => w[key] !== DEFAULTS[key])

  const ranked = useMemo(() => scored.map((req) => ({ req, value: composite(req.score!, w) }))
    .sort((a, b) => b.value - a.value).map((x, i) => ({ ...x, rank: i + 1 })), [scored, w])

  if (!scored.length) {
    return <p className="rounded-2xl border border-dashed border-border bg-card p-6 text-sm text-muted-foreground">No requirement has a score yet. Ask the research chat to derive requirements and rank them.</p>
  }
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="weights-h" className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-xs">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 id="weights-h" className="text-lg">What matters most</h2>
            <p className="text-sm text-muted-foreground">Move a slider to see how the ranking changes. This is a what-if; nothing is saved.</p>
          </div>
          <Button variant="outline" disabled={!changed} onClick={() => setW(DEFAULTS)}><RotateCcw aria-hidden /> Reset</Button>
        </div>
        <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {LABELS.map(({ key, label, help }) => (
            <div key={key} className="flex flex-col gap-2">
              <div className="flex justify-between text-sm"><span id={`w-${key}`} className="font-medium">{label}</span><span className="tabular-nums text-muted-foreground">{pct(w[key])}</span></div>
              <Slider min={0} max={100} step={5} value={[Math.round(w[key] * 100)]} thumbLabel={label}
                onValueChange={(v) => setW({ ...w, [key]: (Array.isArray(v) ? v[0] : v) / 100 })} />
              <span className="text-xs text-muted-foreground">{help}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <section aria-labelledby="rank-h" className="flex flex-col gap-3">
          <h2 id="rank-h" className="text-lg">Ranked requirements</h2>
          <ol className="flex flex-col gap-2">
            {ranked.map(({ req, value, rank }) => {
              const tier = tierFor(value)
              return (
                <li key={req.id} data-testid="ranked" className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3 shadow-xs">
                  <span className="grid size-8 shrink-0 place-items-center rounded-full bg-accent text-sm font-semibold text-accent-foreground">{rank}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{req.title}</p>
                    <p className="text-xs text-muted-foreground">{`Customer ${pct(req.score!.customer_relevance)} · Business ${pct(req.score!.business_signal)} · ${req.code}`}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-base font-semibold tabular-nums">{value.toFixed(2)}</p>
                    <Badge variant={tier === 'Tier 1' ? 'default' : 'outline'} title={TIER_HELP[tier]}>{`${tier}: ${TIER_HELP[tier]}`}</Badge>
                  </div>
                </li>
              )
            })}
          </ol>
          {unscored.length > 0 && <p className="text-sm text-muted-foreground">{`${unscored.length} requirement${unscored.length === 1 ? ' has' : 's have'} no score yet: ${unscored.map((r) => r.code).join(', ')}.`}</p>}
        </section>
        <section aria-labelledby="map-h" className="flex flex-col gap-3">
          <h2 id="map-h" className="text-lg">Customer and business</h2>
          <PriorityMap rows={ranked} />
        </section>
      </div>
    </div>
  )
}
