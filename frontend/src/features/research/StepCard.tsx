import { Badge } from '@/components/ui/badge'
import type { ChatMessage, RunStep } from '@/types/api'
import { CitationChip } from '@/features/sources/CitationChip'
import { findingsOf } from '@/features/sources/citations'

/** One agent's result, as the Critic passed it on. Read-only: the orchestrator decides what happens next. */
export function StepCard({ message, step }: { message: ChatMessage; step: RunStep | undefined }) {
  const agent = String(message.payload.agent ?? step?.agent_name ?? 'Agent')
  const failed = message.payload.failed === true
  const cited = findingsOf(message)
  const findings = (message.payload.output as { findings?: unknown[] } | null | undefined)?.findings
  return (
    <article className="flex flex-col gap-2 border border-border p-5" aria-label={`${agent} result`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base">{agent}</h3>
        {failed && <Badge variant="destructive">Failed</Badge>}
        {Array.isArray(findings) && <Badge variant="outline">{`${findings.length} findings`}</Badge>}
      </div>
      <p className="whitespace-pre-line text-sm">{message.content}</p>
      {cited.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-bold text-primary">{`Findings and sources (${cited.length})`}</summary>
          <ul className="mt-2 flex flex-col gap-2">
            {cited.map((f) => (
              <li key={f.id} className="border-l-2 border-border pl-3">
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
