import { AlertTriangle, Bot } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ChatMessage, RunStep } from '@/types/api'
import { CitationChip } from '@/features/sources/CitationChip'
import { findingsOf } from '@/features/sources/citations'

/** One agent's result, as the Critic passed it on. Read-only: the orchestrator decides what happens next. */
export function StepCard({ message, step }: { message: ChatMessage; step: RunStep | undefined }) {
  const agent = String(message.payload.agent ?? step?.agent_name ?? 'Agent')
  const failed = message.payload.failed === true
  const findings = findingsOf(message)
  const Icon = failed ? AlertTriangle : Bot
  return (
    <article className="rise sm:ml-11 flex flex-col gap-2.5 rounded-2xl border border-border bg-canvas-tint p-4" aria-label={`${agent} result`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={failed ? 'grid size-7 place-items-center rounded-lg bg-destructive/10 text-destructive' : 'grid size-7 place-items-center rounded-lg bg-primary/10 text-primary'}>
          <Icon className="size-4" />
        </span>
        <h3 className="text-sm">{agent}</h3>
        {failed && <Badge variant="destructive">Failed</Badge>}
        {findings.length > 0 && <Badge variant="outline" className="bg-background">{`${findings.length} findings`}</Badge>}
      </div>
      <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90">{message.content}</p>
      {findings.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-medium text-primary">{`Findings and sources (${findings.length})`}</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {findings.map((f) => (
              <li key={f.id} className="border-l-2 border-border pl-3 leading-relaxed">
                {f.text}
                {f.refs.slice(0, 4).map((r, i) => <CitationChip key={i} n={i + 1} sourceRef={r} />)}
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  )
}
