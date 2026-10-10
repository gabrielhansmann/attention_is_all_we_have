import type { Citation } from '@/types/api'

// The quote is the verbatim stored text, so a reader can check a claim against its source.
export function CitationBlock({ citation }: { citation: Citation }) {
  return (
    <figure className="border-l-2 border-primary bg-muted px-4 py-3">
      <blockquote className="text-sm text-foreground">{citation.quote}</blockquote>
      <figcaption className="mt-2 text-xs tracking-wide text-muted-foreground">
        <span className="font-bold text-foreground">{citation.file}</span>
        <span>{`, ${citation.locator}`}</span>
      </figcaption>
    </figure>
  )
}
