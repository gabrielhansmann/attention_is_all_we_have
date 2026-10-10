import { Badge } from '@/components/ui/badge'
import type { ChatMessage, RunStep } from '@/types/api'

/** One agent's result, as the Critic passed it on. Read-only: the orchestrator decides what happens next. */
export function StepCard({ message, step }: { message: ChatMessage; step: RunStep | undefined }) {
  const agent = String(message.payload.agent ?? step?.agent_name ?? 'Agent')
  const failed = message.payload.failed === true
  const findings = (message.payload.output as { findings?: unknown[] } | null | undefined)?.findings
  return (
    <article className="flex flex-col gap-2 border border-border p-5" aria-label={`${agent} result`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base">{agent}</h3>
        {failed && <Badge variant="destructive">Failed</Badge>}
        {Array.isArray(findings) && <Badge variant="outline">{`${findings.length} findings`}</Badge>}
      </div>
      <p className="whitespace-pre-line text-sm">{message.content}</p>
    </article>
  )
}
