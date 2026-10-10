import { CitationBlock } from '@/components/evidence/CitationBlock'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { Hit } from '@/types/api'

const CHIPS = ['vehicle_line', 'market_code', 'powertrain', 'polarity', 'domain', 'heading'] as const

export function HitCard({ hit }: { hit: Hit }) {
  const sim = typeof hit.meta.similarity === 'number' ? hit.meta.similarity : null
  return (
    <Card className="rounded-2xl bg-background shadow-xs">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {CHIPS.map((k) => (hit.meta[k] ? <Badge key={k} variant="outline">{String(hit.meta[k])}</Badge> : null))}
          {sim !== null && <span className="ml-auto text-xs text-muted-foreground">{`Similarity ${sim.toFixed(2)}`}</span>}
        </div>
        <p className="text-sm">{hit.text.length > 600 ? `${hit.text.slice(0, 600)}...` : hit.text}</p>
        <CitationBlock citation={hit.citation} />
      </CardContent>
    </Card>
  )
}
