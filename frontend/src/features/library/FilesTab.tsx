import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { SourceInfo } from '@/types/api'
import { contents } from './format'
import { UploadForm } from './UploadForm'

interface Props {
  files: SourceInfo[]
  lines: string[]
  onStored: () => void
}

/** The loaded files and the form that adds one. The form stays closed until it is asked for. */
export function FilesTab({ files, lines, onStored }: Props) {
  const [adding, setAdding] = useState(false)
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted-foreground">
          PDF and Excel files in the evidence store. Every row an agent cites points back to one of them.
        </p>
        <Button variant={adding ? 'outline' : 'default'} onClick={() => setAdding((a) => !a)} aria-expanded={adding} aria-controls="upload-form">
          {adding ? <X /> : <Plus />} {adding ? 'Close' : 'Add a file'}
        </Button>
      </div>
      {adding && <div id="upload-form"><UploadForm lines={lines} loaded={files.map((f) => f.file)} onStored={onStored} /></div>}
      {files.length === 0 ? (
        <p className="rounded-2xl border border-border bg-background p-6 text-sm text-muted-foreground">No source files are loaded yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-border bg-background shadow-xs" tabIndex={0} role="region" aria-label="Sources table, scrolls sideways on small screens">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <caption className="sr-only">Source files loaded into the evidence store</caption>
            <thead>
              <tr className="border-b border-border bg-canvas-tint text-left">
                <th scope="col" className="p-3 font-semibold">File</th>
                <th scope="col" className="p-3 font-semibold">Kind</th>
                <th scope="col" className="p-3 font-semibold">Line</th>
                <th scope="col" className="p-3 font-semibold">Contents</th>
              </tr>
            </thead>
            <tbody>
              {files.map((s) => (
                <tr key={s.id} className="border-b border-border align-top last:border-b-0">
                  <th scope="row" className="p-3 text-left font-semibold">{s.file}</th>
                  <td className="p-3">{s.family}</td>
                  <td className="p-3">{s.vehicle_line ?? 'Several'}</td>
                  <td className="p-3">{contents(s.counts)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
