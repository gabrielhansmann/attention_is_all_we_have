import { AlertTriangle, Bot } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import type { ChatMessage, RunStep } from '@/types/api'
import { CitationChip } from '@/features/sources/CitationChip'
import { Prose } from '@/features/sources/Prose'
import { findingsOf, indexOf } from '@/features/sources/citations'

/** Pipeline stage of each agent. Mirrors backend/app/orchestration/catalog.py. */
const STAGE: Record<string, string> = {
  'Baseline Agent': 'Research', 'Customer Feedback Agent': 'Research', 'Sales & Portfolio Agent': 'Research',
  'Competitor Agent': 'Research', 'Market & Trend Agent': 'Research', 'Clustering Agent': 'Structure',
  'Requirements Drafting Agent': 'Requirements', 'Prioritization Agent': 'Prioritization', 'Documentation Agent': 'Documentation',
}

/** The first line of an agent summary is the lead; the rest is detail. */
function split(content: string): [string, string] {
  const [lead, ...rest] = content.trim().split('\n')
  return [lead, rest.join('\n').trim()]
}

/** One agent's result, as the Critic passed it on. Read-only: the orchestrator decides what happens next. */
export function StepCard({ message, step }: { message: ChatMessage; step: RunStep | undefined }) {
  const agent = String(message.payload.agent ?? step?.agent_name ?? 'Agent')
  const failed = message.payload.failed === true
  const findings = findingsOf(message)
  const stage = STAGE[agent]
  const [lead, detail] = split(message.content)
  const Icon = failed ? AlertTriangle : Bot
  return (
    <article className="rise sm:ml-11 flex flex-col gap-3 rounded-2xl border border-border bg-canvas-tint p-4" aria-label={`${agent} result`}>
      <div className="flex items-start gap-2.5">
        <span className={failed ? 'grid size-8 shrink-0 place-items-center rounded-lg bg-destructive/10 text-destructive' : 'grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary'}>
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-sm">{agent}</h3>
            {stage && <Badge variant="outline" className="bg-background">{stage}</Badge>}
            {failed && <Badge variant="destructive">Failed</Badge>}
            {findings.length > 0 && <Badge variant="outline" className="bg-background">{`${findings.length} finding${findings.length === 1 ? '' : 's'}`}</Badge>}
          </div>
        </div>
      </div>

      <Prose text={lead} findings={indexOf(findings)} className="text-sm" />

      {detail && (
        <details className="group text-sm">
          <summary className="w-fit cursor-pointer font-medium text-primary focus-visible:outline-2 focus-visible:outline-ring">
            <span className="group-open:hidden">Show full summary</span><span className="hidden group-open:inline">Hide full summary</span>
          </summary>
          <div className="mt-3 rounded-xl bg-background p-3.5"><Prose text={detail} findings={indexOf(findings)} className="text-sm" /></div>
        </details>
      )}

      {findings.length > 0 && (
        <details className="text-sm">
          <summary className="w-fit cursor-pointer font-medium text-primary focus-visible:outline-2 focus-visible:outline-ring">{`Findings and sources (${findings.length})`}</summary>
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
