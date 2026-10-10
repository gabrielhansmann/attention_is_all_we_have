import { useSourceViewer } from './SourceViewer'
import type { SourceRef } from './citations'

/** A numbered marker next to a claim. Hover or focus previews the quote, click opens the source panel. */
export function CitationChip({ n, sourceRef }: { n: number | string; sourceRef: SourceRef }) {
  const open = useSourceViewer()
  return (
    <span className="group relative inline-block align-baseline">
      <button type="button" onClick={() => open(sourceRef)}
        aria-label={`Source ${n}: ${sourceRef.file}, ${sourceRef.locator}`}
        className="mx-0.5 min-w-5 border border-border bg-muted px-1 text-xs font-bold text-primary hover:border-primary focus-visible:outline-2 focus-visible:outline-ring">
        {n}
      </button>
      <span role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-0 z-40 mb-1 w-72 border border-border bg-background p-3 text-left text-xs shadow-md group-focus-within:visible group-hover:visible">
        <span className="block font-bold text-foreground">{sourceRef.file}</span>
        <span className="block text-muted-foreground">{sourceRef.locator}</span>
        {sourceRef.quote && <span className="mt-1 line-clamp-4 block text-foreground">{sourceRef.quote}</span>}
      </span>
    </span>
  )
}
