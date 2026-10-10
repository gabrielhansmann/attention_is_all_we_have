import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

// Shell for the chat workspace described in docs/architecture/02 and decision 0005:
// a request starts a run, the orchestrator shows a plan, each agent's step card appears in the thread
// and the PM accepts, edits, retries or rejects it before the next agent starts.
// The orchestrator is not connected yet, so this page shows the real empty state and nothing invented.
export function ChatPage() {
  return (
    <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
      <aside aria-labelledby="conv-h" className="flex flex-col gap-3 border border-border p-6 self-start">
        <h2 id="conv-h" className="text-xl">Conversations</h2>
        <p className="text-sm text-muted-foreground">No conversations yet.</p>
      </aside>

      <section aria-labelledby="chat-h" className="flex flex-col gap-6">
        <div>
          <h1 id="chat-h" className="text-[32px] leading-tight">Start a research request</h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Describe what you want to know. The orchestrator picks the agents that are needed and shows its plan.
            Each agent runs on its own, and you accept, edit, retry or reject its answer before the next one starts.
          </p>
        </div>

        <form onSubmit={(e) => e.preventDefault()} className="flex flex-col gap-3 border border-border p-6">
          <Label htmlFor="request">Research request</Label>
          <Textarea id="request" rows={4} disabled
            placeholder="For example: What would we need to stay competitive on seat comfort in the US?" />
          <p className="text-sm text-muted-foreground">
            The orchestrator is not connected yet, so requests cannot be sent. You can already{' '}
            <Link to="/evidence" className="text-primary underline underline-offset-4">search the evidence</Link>.
          </p>
          <div>
            <Button type="submit" size="lg" disabled>Send request</Button>
          </div>
        </form>
      </section>
    </div>
  )
}
