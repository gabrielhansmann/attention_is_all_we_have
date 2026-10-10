import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { ExternalLink, FileText, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError, fetchSourceFile } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { EvidenceContext } from '@/types/api'
import type { SourceRef } from './citations'

const SourceViewerContext = createContext<(ref: SourceRef) => void>(() => {})
export const useSourceViewer = () => useContext(SourceViewerContext)

type Load = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: EvidenceContext }

/** Opens the original file in a new tab, at the cited page for a PDF. */
async function openOriginal(ctx: EvidenceContext): Promise<void> {
  if (!ctx.document) return
  const blob = await fetchSourceFile(ctx.document.source_id)
  const url = URL.createObjectURL(blob)
  window.open(ctx.page ? `${url}#page=${ctx.page}` : url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

function Panel({ sourceRef, onClose }: { sourceRef: SourceRef; onClose: () => void }) {
  const [load, setLoad] = useState<Load>(sourceRef.kind && sourceRef.id ? { kind: 'loading' } : { kind: 'error', message: '' })
  const [openError, setOpenError] = useState<string | null>(null)

  useEffect(() => {
    if (!sourceRef.kind || !sourceRef.id) return
    const ctrl = new AbortController()
    api.evidenceContext(sourceRef.kind, sourceRef.id, ctrl.signal)
      .then((data) => setLoad({ kind: 'ok', data }))
      .catch((e) => !(e instanceof DOMException) && setLoad({ kind: 'error', message: e instanceof ApiError ? e.message : 'Could not load the source.' }))
    return () => ctrl.abort()
  }, [sourceRef])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const ctx = load.kind === 'ok' ? load.data : null
  return (
    <aside role="dialog" aria-label="Source" data-testid="source-panel"
      className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-background sm:w-[440px]">
      <header className="flex items-start gap-3 border-b border-border p-4">
        <FileText className="mt-1 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="break-words text-base">{sourceRef.file}</h2>
          <p className="text-xs text-muted-foreground">{ctx?.title ? `${ctx.title}, ${sourceRef.locator}` : sourceRef.locator}</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close source"><X className="size-4" /></Button>
      </header>

      <div className="flex-1 overflow-y-auto p-4">
        {load.kind === 'loading' && <Skeleton className="h-40 w-full" aria-label="Loading source" />}
        {load.kind === 'error' && (
          <div className="flex flex-col gap-3">
            {load.message && <p role="alert" className="text-sm text-destructive">{load.message}</p>}
            {sourceRef.quote && <blockquote className="border-l-2 border-primary bg-muted px-4 py-3 text-sm">{sourceRef.quote}</blockquote>}
          </div>
        )}
        {ctx && (
          <ol className="flex flex-col gap-2">
            {ctx.passages.map((p) => (
              <li key={p.id} aria-current={p.cited ? 'true' : undefined}
                className={cn('px-3 py-2 text-sm', p.cited ? 'border-l-2 border-primary bg-primary/10' : 'text-muted-foreground')}>
                {p.label && <span className="mb-1 block text-xs tracking-wide text-muted-foreground">{p.label}</span>}
                <span className="whitespace-pre-line">{p.text}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {ctx?.document?.url && (
        <footer className="border-t border-border p-4">
          <a href={ctx.document.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-2 text-sm font-medium text-primary underline-offset-4 hover:underline">
            <ExternalLink className="size-4" aria-hidden /> Open website <span className="sr-only">(opens in a new tab)</span>
          </a>
        </footer>
      )}
      {ctx?.document && !ctx.document.url && (
        <footer className="flex flex-col gap-2 border-t border-border p-4">
          <Button variant="outline" disabled={!ctx.document.openable}
            onClick={() => openOriginal(ctx).catch((e) => setOpenError(e instanceof ApiError ? e.message : 'Could not open the file.'))}>
            <ExternalLink className="size-4" aria-hidden />
            {ctx.page ? `Open original, page ${ctx.page}` : 'Open original file'}
          </Button>
          {!ctx.document.openable && <p className="text-xs text-muted-foreground">The original file is not on this server.</p>}
          {openError && <p role="alert" className="text-xs text-destructive">{openError}</p>}
        </footer>
      )}
    </aside>
  )
}

export function SourceViewerProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<SourceRef | null>(null)
  const close = useCallback(() => setCurrent(null), [])
  return (
    <SourceViewerContext.Provider value={setCurrent}>
      {children}
      {current && <Panel sourceRef={current} onClose={close} />}
    </SourceViewerContext.Provider>
  )
}
