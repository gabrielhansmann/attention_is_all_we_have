import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/** Scrollable page body with a title row, used by the non-chat views. */
export function PageShell({ title, description, Icon, children, testId }: { title: string; description: string; Icon: LucideIcon; children: ReactNode; testId?: string }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-canvas-tint" data-testid={testId}>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-8">
        <header className="flex items-start gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary" aria-hidden><Icon className="size-5" /></span>
          <div>
            <h1 className="text-2xl">{title}</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>
          </div>
        </header>
        {children}
      </div>
    </div>
  )
}
