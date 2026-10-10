import { Fragment, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { CitationChip } from './CitationChip'
import type { Finding } from './citations'

/** The markdown the agents write: headings, paragraphs, nested bullet and numbered lists, tables, bold and code.
 *  A `[finding-id]` marker that matches a known finding becomes a numbered source chip; any other bracket is left as written. */

type Item = { text: string; children: Item[] }
type Block =
  | { t: 'h'; level: number; text: string }
  | { t: 'label'; text: string }
  | { t: 'p'; lines: string[] }
  | { t: 'list'; ordered: boolean; items: Item[] }
  | { t: 'table'; head: string[]; rows: string[][] }

const LIST = /^(\s*)([-*]|\d+[.)])\s+(.*)/
const HEADING = /^(#{1,4})\s+(.*)/
const isRule = (l: string) => /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(l) && l.includes('-')
const cells = (l: string) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map((c) => c.replace(/\\\|/g, '|').trim())

function parseList(lines: string[], start: number): [Block, number] {
  const ordered = /\d/.test(LIST.exec(lines[start])![2])
  const root: Item[] = []
  // One entry per nesting level: the indent its items sit at, and where they go.
  const stack: { indent: number; items: Item[] }[] = []
  let i = start
  for (; i < lines.length; i++) {
    const m = LIST.exec(lines[i])
    if (!m) break
    const indent = m[1].replace(/\t/g, '    ').length
    const item: Item = { text: m[3], children: [] }
    if (!stack.length) stack.push({ indent, items: root })
    let top = stack[stack.length - 1]
    if (indent > top.indent && top.items.length) {
      const parent = top.items[top.items.length - 1]
      top = { indent, items: parent.children }
      stack.push(top)
    } else {
      while (stack.length > 1 && indent < top.indent) { stack.pop(); top = stack[stack.length - 1] }
    }
    top.items.push(item)
  }
  return [{ t: 'list', ordered, items: root }, i]
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r/g, '').split('\n')
  const blocks: Block[] = []
  let para: string[] = []
  const flush = () => { if (para.length) blocks.push({ t: 'p', lines: para }); para = [] }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line.trim()) { flush(); continue }
    const h = HEADING.exec(line)
    if (h) { flush(); blocks.push({ t: 'h', level: h[1].length, text: h[2].trim() }); continue }
    if (line.trim().startsWith('|') && i + 1 < lines.length && isRule(lines[i + 1])) {
      flush()
      const head = cells(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(cells(lines[i++]))
      i--
      blocks.push({ t: 'table', head, rows })
      continue
    }
    if (LIST.test(line)) {
      flush()
      const [block, next] = parseList(lines, i)
      blocks.push(block)
      i = next - 1
      continue
    }
    // "Findings (what must carry over):" directly above a list is a small heading, not a sentence.
    if (line.trimEnd().endsWith(':') && line.length < 90 && LIST.test(lines[i + 1] ?? '')) { flush(); blocks.push({ t: 'label', text: line.trim().slice(0, -1) }); continue }
    para.push(line)
  }
  flush()
  return blocks
}

type Options = { findings: Map<string, Finding>; compact?: boolean }

function useInline({ findings }: Options) {
  const numbers = new Map<string, number>()
  const chips = (id: string): ReactNode => {
    const f = findings.get(id)
    if (!f || !f.refs.length) return `[${id}]`
    if (!numbers.has(id)) numbers.set(id, numbers.size + 1)
    return f.refs.slice(0, 3).map((r, i) => <CitationChip key={i} n={i === 0 ? numbers.get(id)! : `${numbers.get(id)}.${i + 1}`} sourceRef={r} />)
  }
  return (s: string): ReactNode[] =>
    s.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]\s]+\])/g).map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <code key={i} className="rounded bg-muted px-1 py-0.5 text-[0.85em]">{part.slice(1, -1)}</code>
      const m = part.match(/^\[([^\]\s]+)\]$/)
      if (m && !findings.has(m[1]) && /^[a-z][a-z_ -]*$/.test(m[1])) {
        return <span key={i} className="mr-1.5 inline-block rounded-full bg-muted px-2 py-0.5 align-baseline text-[0.7rem] font-medium capitalize text-muted-foreground">{m[1].replace(/_/g, ' ')}</span>
      }
      return m ? <Fragment key={i}>{chips(m[1])}</Fragment> : <Fragment key={i}>{part}</Fragment>
    })
}


const SOURCE_PART = /\.(xlsx|pdf|csv|docx?)\b|^\+\d+ more/i

/** Agents end a finding with "(Interpreted; market US; n=2 of 1594 comments; file, row 12; file, row 13)". Keep the facts, fold the file rows into a count. */
function splitMeta(text: string): [string, string | null] {
  if (!text.endsWith(')')) return [text, null]
  let depth = 0
  for (let i = text.length - 1; i >= 0; i--) {
    if (text[i] === ')') depth++
    else if (text[i] === '(' && --depth === 0) {
      const parts = text.slice(i + 1, -1).split(';').map((x) => x.trim()).filter(Boolean)
      if (parts.length < 2 || !parts.some((x) => SOURCE_PART.test(x))) return [text, null]
      const facts = parts.filter((x) => !SOURCE_PART.test(x))
      const rows = parts.length - facts.length
      return [text.slice(0, i).trimEnd(), [...facts, `${rows} cited row${rows === 1 ? '' : 's'}`].join(' · ')]
    }
  }
  return [text, null]
}

function ListView({ items, ordered, inline }: { items: Item[]; ordered: boolean; inline: (s: string) => ReactNode[] }) {
  const Tag = ordered ? 'ol' : 'ul'
  return (
    <Tag className={ordered ? 'flex list-decimal flex-col gap-1.5 pl-5 marker:text-muted-foreground' : 'flex list-disc flex-col gap-1.5 pl-5 marker:text-muted-foreground'}>
      {items.map((it, i) => (
        <li key={i} className="pl-1">
          {(() => {
            const [main, meta] = splitMeta(it.text)
            return <>{inline(main)}{meta && <span className="mt-0.5 block text-xs text-muted-foreground">{meta}</span>}</>
          })()}
          {it.children.length > 0 && <div className="mt-1.5"><ListView items={it.children} ordered={false} inline={inline} /></div>}
        </li>
      ))}
    </Tag>
  )
}

function BlockView({ block, inline }: { block: Block; inline: (s: string) => ReactNode[] }) {
  switch (block.t) {
    case 'h':
      return <h3 className={block.level === 1 ? 'text-lg' : block.level === 2 ? 'mt-3 border-t border-border pt-4 text-base' : 'mt-1 text-sm'}>{inline(block.text)}</h3>
    case 'label':
      return <h4 className="mt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{inline(block.text)}</h4>
    case 'p':
      return <p className="whitespace-pre-line">{block.lines.map((l, i) => <Fragment key={i}>{i > 0 && '\n'}{inline(l)}</Fragment>)}</p>
    case 'list':
      return <ListView items={block.items} ordered={block.ordered} inline={inline} />
    case 'table':
      return (
        <div tabIndex={0} role="region" aria-label="Table" className="overflow-x-auto rounded-xl border border-border focus-visible:outline-2 focus-visible:outline-ring">
          <table className="w-full min-w-[28rem] text-left text-xs">
            <thead className="bg-canvas-tint text-muted-foreground">
              <tr>{block.head.map((c, i) => <th key={i} scope="col" className="px-3 py-2 font-medium">{inline(c)}</th>)}</tr>
            </thead>
            <tbody>
              {block.rows.map((r, i) => <tr key={i} className="border-t border-border align-top">{r.map((c, j) => <td key={j} className="px-3 py-2">{inline(c)}</td>)}</tr>)}
            </tbody>
          </table>
        </div>
      )
  }
}

/** `collapse` names `##` sections (case-insensitive) that start closed, or `*` for all of them, for reference material such as an audit trail. */
export function Prose({ text, findings, collapse = [], className }: { text: string; findings: Map<string, Finding>; collapse?: string[]; className?: string }) {
  const inline = useInline({ findings })
  const blocks = parseBlocks(text)
  const closed = new Set(collapse.map((c) => c.toLowerCase()))
  const all = closed.has('*')
  const out: ReactNode[] = []
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    if (b.t === 'h' && b.level === 2 && (all || closed.has(b.text.toLowerCase()))) {
      let j = i + 1
      while (j < blocks.length && !(blocks[j].t === 'h' && (blocks[j] as { level: number }).level <= 2)) j++
      const body = blocks.slice(i + 1, j)
      out.push(
        <details key={i} className="group mt-3 border-t border-border pt-3">
          <summary className="flex cursor-pointer items-center gap-1.5 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">
            <ChevronDown className="size-4 -rotate-90 transition-transform group-open:rotate-0" aria-hidden /> {b.text}
          </summary>
          <div className="mt-3 flex flex-col gap-3">{body.map((x, k) => <BlockView key={k} block={x} inline={inline} />)}</div>
        </details>,
      )
      i = j - 1
    } else {
      out.push(<BlockView key={i} block={b} inline={inline} />)
    }
  }
  return <div className={cn('flex flex-col gap-3 text-[0.95rem] leading-relaxed', className)}>{out}</div>
}
