import { Quote } from 'lucide-react'
import type { Citation } from '@/types/api'

// The quote is the verbatim stored text, so a reader can check a claim against its source.
export function CitationBlock({ citation }: { citation: Citation }) {
  return (
    <figure className="flex gap-3 rounded-xl bg-accent/60 px-4 py-3">
      <Quote className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
      <div className="min-w-0">
        <blockquote className="text-sm text-foreground">{citation.quote}</blockquote>
        <figcaption className="mt-2 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">{citation.file}</span>
          <span>{`, ${citation.locator}`}</span>
        </figcaption>
      </div>
    </figure>
  )
}
