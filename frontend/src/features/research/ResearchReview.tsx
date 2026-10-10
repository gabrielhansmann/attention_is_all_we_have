import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CitationChip } from '@/features/sources/CitationChip'
import type { Finding } from '@/features/sources/citations'
import type { ResearchReview as Review } from '@/types/api'

export function ResearchReview({ review, findings }: { review: Review; findings: Map<string, Finding> }) {
  return (
    <section aria-label="Research checks" className="mt-5 border-t border-primary/20 pt-4">
      <h3 className="text-base font-semibold">Research checks</h3>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{review.scope_note}</p>
      <div className="mt-4 flex flex-col gap-4">
        {review.requirements.map((item) => (
          <Card key={item.requirement_id} className="rounded-2xl bg-background shadow-xs">
            <CardHeader>
              <CardTitle>{item.title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {([
                  { label: 'Case for', evidence: item.support, empty: 'No linked, citable support in this run.' },
                  { label: 'Signals to challenge', evidence: item.counter, empty: 'No related counter-signal found in this run. This does not confirm the claim.' },
                ] as const).map(({ label, evidence, empty }) => (
                  <div key={label} className="min-w-0 rounded-xl border border-border p-3">
                    <h4 className="text-sm font-semibold">{label}</h4>
                    {evidence.length ? <ul className="mt-2 space-y-2 text-sm leading-relaxed">
                      {evidence.map((entry) => {
                        const ref = findings.get(entry.finding_id)?.refs[0] ?? { file: entry.source, locator: entry.locator }
                        return <li key={entry.finding_id} className="break-words">
                          {entry.text} <CitationChip n={entry.finding_id.slice(0, 6)} sourceRef={ref} />
                          <span className="block text-xs text-muted-foreground">{entry.market || 'Market unassigned'} · {entry.evidence_level}</span>
                        </li>
                      })}
                    </ul> : <p className="mt-2 text-sm text-muted-foreground">{empty}</p>}
                  </div>
                ))}
              </div>
              <div>
                <h4 className="text-sm font-semibold">Market signals</h4>
                <ul className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {item.markets.map((market) => <li key={market.market} className="min-w-0 rounded-xl bg-canvas-tint p-2 text-xs">
                    <span className="block font-semibold">{market.market}</span>
                    <span className="text-muted-foreground">{market.status}</span>
                    <span className="block text-muted-foreground">{market.finding_ids.length} related finding(s)</span>
                  </li>)}
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-semibold">Next research actions</h4>
                {item.actions.length ? <ol className="mt-2 space-y-2">
                  {item.actions.map((action, index) => <li key={`${action.action}-${index}`} className="flex items-start gap-2 text-sm">
                    <Badge variant="outline" className="shrink-0 capitalize">{action.priority}</Badge>
                    <span><strong>{action.action}.</strong> {action.reason}</span>
                  </li>)}
                </ol> : <p className="mt-2 text-sm text-muted-foreground">No gaps were identified in the linked findings. This is not a validation of the requirement.</p>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}
