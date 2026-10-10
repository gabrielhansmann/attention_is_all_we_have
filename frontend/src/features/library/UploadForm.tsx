import { useState, type FormEvent } from 'react'
import { FilterSelect } from '@/components/evidence/FilterSelect'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/lib/api'
import type { UploadResult } from '@/types/api'
import { contents } from './format'

type State =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'done'; result: UploadResult }
  | { kind: 'error'; message: string }

interface Props {
  lines: string[]
  loaded: string[] // names of the files already in the evidence store
  onStored: () => void
}

/** Adds one PDF or Excel file to the evidence store. The backend decides what the file is from its layout. */
export function UploadForm({ lines, loaded, onStored }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [line, setLine] = useState<string | undefined>()
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [inputKey, setInputKey] = useState(0) // a new key clears the file input after a successful upload
  const busy = state.kind === 'busy'
  const replaces = !!file && loaded.includes(file.name)

  function choose(f: File | null) {
    setFile(f)
    setState({ kind: 'idle' })
    // The provided files carry their vehicle line as a prefix (G60_...): offer it, the person can change it.
    const guess = f && lines.find((l) => f.name.toUpperCase().startsWith(`${l.toUpperCase()}_`))
    if (guess) setLine(guess)
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!file || busy) return
    setState({ kind: 'busy' })
    try {
      const result = await api.uploadSource(file, line, replaces)
      setState({ kind: 'done', result })
      setFile(null)
      setInputKey((k) => k + 1)
      onStored()
    } catch (err) {
      setState({ kind: 'error', message: err instanceof ApiError ? err.message : 'Something went wrong.' })
    }
  }

  return (
    <form onSubmit={submit} aria-labelledby="upload-h" className="flex flex-col gap-4 rounded-2xl border border-border bg-background p-4 shadow-xs sm:p-6">
      <div>
        <h3 id="upload-h" className="text-base font-bold">Add a file</h3>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          PDF or Excel (.xlsx), up to 25 MB. Feedback exports, sales volumes and customer studies are recognised by
          their layout. A PDF is stored as searchable text, and a catalog also as equipment options.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="upload-file">File</Label>
          <Input key={inputKey} id="upload-file" type="file" accept=".pdf,.xlsx" disabled={busy}
            aria-describedby={replaces ? 'upload-replaces' : undefined}
            onChange={(e) => choose(e.target.files?.[0] ?? null)} />
        </div>
        <FilterSelect id="upload-line" label="Vehicle line" value={line} onChange={setLine}
          options={lines.map((l) => ({ value: l, label: l }))} allLabel="Not specific to one line" />
      </div>
      {replaces && (
        <p id="upload-replaces" className="text-sm">
          {`${file.name} is already loaded. Uploading it again replaces the rows stored from it.`}
        </p>
      )}
      <div>
        <Button type="submit" size="lg" disabled={!file || busy}>
          {busy ? 'Storing file' : replaces ? 'Replace file' : 'Upload file'}
        </Button>
      </div>
      {busy && (
        <p role="status" className="text-sm text-muted-foreground">
          Reading and storing the file. A large feedback export can take a minute or two.
        </p>
      )}
      {state.kind === 'done' && (
        <div role="status" className="rounded-2xl border border-border p-4 text-sm">
          <p>{`${state.result.replaced ? 'Replaced' : 'Stored'} ${state.result.file}: ${contents(state.result.counts)}.`}</p>
          {state.result.notes.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-muted-foreground">
              {state.result.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}
        </div>
      )}
      {state.kind === 'error' && (
        <p role="alert" className="rounded-2xl border border-destructive p-4 text-sm text-destructive">{`Upload failed: ${state.message}`}</p>
      )}
    </form>
  )
}
