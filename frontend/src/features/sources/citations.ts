import type { ChatMessage } from '@/types/api'

/** A claim's source. `kind` and `id` are present when the row can be opened in the viewer. */
export interface SourceRef {
  kind?: string
  id?: string
  file: string
  locator: string
  quote?: string
}

export interface Finding {
  id: string
  text: string
  refs: SourceRef[]
}

/** Agents store citations in slightly different shapes; read them all the same way. */
function refsOf(f: Record<string, unknown>): SourceRef[] {
  const list = Array.isArray(f.citations) ? (f.citations as Record<string, unknown>[]) : []
  const refs = list
    .filter((c) => c && (c.file || c.source) && c.locator)
    .map((c) => ({
      kind: typeof c.kind === 'string' ? c.kind : undefined,
      id: typeof c.id === 'string' ? c.id : undefined,
      file: String(c.file ?? c.source),
      locator: String(c.locator),
      quote: typeof c.quote === 'string' ? c.quote : undefined,
    }))
  if (refs.length) return refs
  const file = f.source_file ?? f.source ?? f.file
  return file && f.locator ? [{ file: String(file), locator: String(f.locator) }] : []
}

export function findingsOf(message: ChatMessage): Finding[] {
  return findingsFrom((message.payload.output as { findings?: unknown[] } | null | undefined)?.findings)
}

/** Findings from raw agent output (a step card, or the evidence the API attaches to a requirement). */
export function findingsFrom(raw: unknown): Finding[] {
  if (!Array.isArray(raw)) return []
  return raw.flatMap((f) => {
    const r = f as Record<string, unknown>
    return r && typeof r.text === 'string' && r.id ? [{ id: String(r.id), text: r.text, refs: refsOf(r) }] : []
  })
}

/** Finding id -> finding, across every step of the thread, so a [F-101] marker in the result can be resolved. */
export function findingIndex(messages: ChatMessage[]): Map<string, Finding> {
  const index = new Map<string, Finding>()
  for (const m of messages) if (m.kind === 'step_card') for (const f of findingsOf(m)) index.set(f.id, f)
  return index
}

/** The sources behind a statement. A statement cites finding ids; the finding supplies the openable source. */
export function statementRefs(citations: { finding_id?: string; source?: string; locator?: string }[], index: Map<string, Finding>): SourceRef[] {
  const out: SourceRef[] = []
  for (const c of citations) {
    const found = c.finding_id ? index.get(c.finding_id)?.refs : undefined
    if (found?.length) out.push(...found.slice(0, 1))
    else if (c.source && c.locator) out.push({ file: c.source, locator: c.locator })
  }
  return out
}

export const indexOf = (findings: Finding[]) => new Map(findings.map((f) => [f.id, f]))
