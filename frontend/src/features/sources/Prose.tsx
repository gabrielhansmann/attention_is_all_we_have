import { Fragment, type ReactNode } from 'react'
import { CitationChip } from './CitationChip'
import type { Finding } from './citations'

/** Minimal markdown for the dossier: headings, bullets, bold, tables as plain rows. A `[finding-id]` marker
 *  that matches a known finding becomes a numbered chip; any other bracket is left as written. */
export function Prose({ text, findings }: { text: string; findings: Map<string, Finding> }) {
  const numbers = new Map<string, number>()
  const chips = (id: string): ReactNode => {
    const f = findings.get(id)
    if (!f || !f.refs.length) return `[${id}]`
    if (!numbers.has(id)) numbers.set(id, numbers.size + 1)
    return f.refs.slice(0, 3).map((r, i) => <CitationChip key={i} n={i === 0 ? numbers.get(id)! : `${numbers.get(id)}.${i + 1}`} sourceRef={r} />)
  }
  const inline = (s: string): ReactNode[] =>
    s.split(/(\*\*[^*]+\*\*|\[[^\]\s]+\])/g).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
      const m = part.match(/^\[([^\]\s]+)\]$/)
      return m ? <Fragment key={i}>{chips(m[1])}</Fragment> : <Fragment key={i}>{part}</Fragment>
    })

  return (
    <div className="flex flex-col gap-1 text-sm">
      {text.split('\n').map((line, i) => {
        if (!line.trim()) return null
        const h = line.match(/^(#{1,3})\s+(.*)/)
        if (h) return <h3 key={i} className={h[1].length === 1 ? 'mt-2 text-lg' : 'mt-3 text-base'}>{inline(h[2])}</h3>
        if (/^\s*[-*]\s+/.test(line)) return <p key={i} className="pl-4 -indent-3">{'• '}{inline(line.replace(/^\s*[-*]\s+/, ''))}</p>
        if (/^\|[\s|:-]+\|$/.test(line)) return null
        return <p key={i} className={line.startsWith('|') ? 'text-xs text-muted-foreground' : undefined}>{inline(line)}</p>
      })}
    </div>
  )
}
