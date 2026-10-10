import { useState, type FormEvent } from 'react'
import { ExternalLink } from 'lucide-react'
import { FilterSelect } from '@/components/evidence/FilterSelect'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { api, ApiError } from '@/lib/api'
import type { SourceInfo, TrustTier, UploadResult, WebFind, WebSourceRequest } from '@/types/api'
import { TIER_OPTIONS, clip, domainOf, errorText, fmt, fmtDate, tierLabel, type Load } from './format'

// `list` is set when the page was stored from the "Read by agents" table, so the outcome is reported there.
type State =
  | { kind: 'idle' }
  | { kind: 'busy'; url: string; list: boolean }
  | { kind: 'done'; result: UploadResult; list: boolean }
  | { kind: 'error'; message: string; stored: boolean; list: boolean }

interface Props {
  websites: SourceInfo[]
  found: Load<WebFind[]>
  lines: string[]
  markets: string[]
  onChanged: () => void
}

const PageLink = ({ url, children }: { url: string; children: string }) => (
  <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1.5 font-semibold text-foreground underline-offset-4 hover:underline">
    <span className="break-words">{children}</span>
    <ExternalLink className="mt-1 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
    <span className="sr-only">(opens in a new tab)</span>
  </a>
)

/** Web pages as evidence: add one by address, see what is stored, and see what the web agents read during runs. */
export function WebsitesTab({ websites, found, lines, markets, onChanged }: Props) {
  const [url, setUrl] = useState('')
  const [line, setLine] = useState<string | undefined>()
  const [market, setMarket] = useState<string | undefined>()
  const [tier, setTier] = useState<string | undefined>()
  const [state, setState] = useState<State>({ kind: 'idle' })
  const [removing, setRemoving] = useState<string | null>(null)   // id of the website waiting for a second click
  const [removeError, setRemoveError] = useState<string | null>(null)
  const busy = state.kind === 'busy'
  const again = state.kind === 'error' && state.stored && !state.list

  async function store(body: WebSourceRequest, list = false) {
    setState({ kind: 'busy', url: body.url, list })
    try {
      const result = await api.addWebsite(body)
      setState({ kind: 'done', result, list })
      if (!list) setUrl('')
      onChanged()
    } catch (e) {
      setState({ kind: 'error', message: errorText(e), stored: e instanceof ApiError && e.status === 409, list })
    }
  }

  const outcome = (list: boolean) => (state.kind === 'idle' || state.list !== list ? null : (
    <>
      {state.kind === 'busy' && <p role="status" className="text-sm text-muted-foreground">{`Fetching and storing ${domainOf(state.url)}. This takes a few seconds.`}</p>}
      {state.kind === 'done' && (
        <div role="status" className="rounded-2xl border border-border bg-background p-4 text-sm">
          <p>{`${state.result.replaced ? 'Fetched again' : 'Stored'} ${domainOf(state.result.file)}: ${fmt(state.result.counts.pdf_chunks)} text passages.`}</p>
          {state.result.notes.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-muted-foreground">{state.result.notes.map((n) => <li key={n}>{n}</li>)}</ul>
          )}
        </div>
      )}
      {state.kind === 'error' && (
        <p role="alert" className="rounded-2xl border border-destructive bg-background p-4 text-sm text-destructive">{`Not stored: ${state.message}`}</p>
      )}
    </>
  ))

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!url.trim() || busy) return
    void store({ url: url.trim(), line, market, trust_tier: tier as TrustTier | undefined, replace: again })
  }

  async function remove(id: string) {
    setRemoveError(null)
    try {
      await api.removeWebsite(id)
      setRemoving(null)
      onChanged()
    } catch (e) {
      setRemoveError(errorText(e))
    }
  }

  const unstored = found.kind === 'ok' ? found.data : []
  return (
    <>
      <form onSubmit={submit} aria-labelledby="website-h" className="flex flex-col gap-4 rounded-2xl border border-border bg-background p-4 shadow-xs sm:p-6">
        <div>
          <h2 id="website-h" className="text-base">Add a website</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            The page behind the address is fetched once and stored as searchable text passages, each one citable.
            Only that page is read. Pages that need a login or build their content with JavaScript cannot be stored.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="website-url">Web address</Label>
          <Input id="website-url" type="url" inputMode="url" autoComplete="off" required disabled={busy} value={url}
            aria-describedby="website-url-help"
            onChange={(e) => { setUrl(e.target.value); if (state.kind !== 'busy') setState({ kind: 'idle' }) }} />
          <p id="website-url-help" className="text-xs text-muted-foreground">Starts with https://, for example a review, a press release or a forum thread.</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <FilterSelect id="website-line" label="Vehicle line" value={line} onChange={setLine}
            options={lines.map((l) => ({ value: l, label: l }))} allLabel="Not specific to one line" />
          <FilterSelect id="website-market" label="Market" value={market} onChange={setMarket}
            options={markets.map((m) => ({ value: m, label: m }))} allLabel="Not specific to one market" />
          <FilterSelect id="website-tier" label="Kind of site" value={tier} onChange={setTier}
            options={TIER_OPTIONS} allLabel="Decide from the address" />
        </div>
        <div>
          <Button type="submit" size="lg" disabled={!url.trim() || busy}>
            {busy ? 'Fetching page' : again ? 'Fetch again' : 'Add website'}
          </Button>
        </div>
        {outcome(false)}
      </form>

      <section aria-labelledby="stored-web-h" className="flex flex-col gap-3">
        <h2 id="stored-web-h" className="text-lg">Stored websites</h2>
        {websites.length === 0 ? (
          <p className="rounded-2xl border border-border bg-background p-6 text-sm text-muted-foreground">
            No websites are stored yet. Add one above, or store a page an agent has read.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-border bg-background shadow-xs" tabIndex={0} role="region" aria-label="Stored websites table, scrolls sideways on small screens">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <caption className="sr-only">Websites stored in the evidence store</caption>
              <thead>
                <tr className="border-b border-border bg-canvas-tint text-left">
                  <th scope="col" className="p-3 font-semibold">Page</th>
                  <th scope="col" className="p-3 font-semibold">Kind of site</th>
                  <th scope="col" className="p-3 font-semibold">Scope</th>
                  <th scope="col" className="p-3 font-semibold">Stored</th>
                  <th scope="col" className="p-3 font-semibold"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {websites.map((s) => (
                  <tr key={s.id} className="border-b border-border align-top last:border-b-0">
                    <th scope="row" className="max-w-xs p-3 text-left font-normal">
                      <PageLink url={s.file}>{clip(s.title || domainOf(s.file), 90)}</PageLink>
                      <span className="block break-all text-xs text-muted-foreground">{clip(s.file, 80)}</span>
                    </th>
                    <td className="p-3">{tierLabel(s.trust_tier)}</td>
                    <td className="p-3">{[s.vehicle_line, s.market].filter(Boolean).join(', ') || 'General'}</td>
                    <td className="p-3">
                      {`${fmt(s.counts.pdf_chunks)} passages`}
                      <span className="block text-xs text-muted-foreground">{fmtDate(s.retrieved_at)}</span>
                    </td>
                    <td className="p-3 text-right">
                      {removing === s.id ? (
                        <span className="inline-flex flex-wrap justify-end gap-2">
                          <Button variant="destructive" onClick={() => remove(s.id)}>Remove page</Button>
                          <Button variant="ghost" onClick={() => { setRemoving(null); setRemoveError(null) }}>Keep</Button>
                        </span>
                      ) : (
                        <Button variant="ghost" aria-label={`Remove ${domainOf(s.file)}`} onClick={() => { setRemoving(s.id); setRemoveError(null) }}>Remove</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {removeError && <p role="alert" className="text-sm text-destructive">{`Not removed: ${removeError}`}</p>}
      </section>

      <section aria-labelledby="found-web-h" className="flex flex-col gap-3">
        <div>
          <h2 id="found-web-h" className="text-lg">Read by agents</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Websites the Market &amp; Trend and Competitor agents read during research runs. An agent keeps only a short
            snapshot. Store a page to make its full text searchable and citable.
          </p>
        </div>
        {found.kind === 'loading' && <p role="status" className="text-sm text-muted-foreground">Loading websites read by agents.</p>}
        {found.kind === 'error' && (
          <p role="alert" className="rounded-2xl border border-destructive p-4 text-sm text-destructive">{`Agent websites unavailable: ${found.message}`}</p>
        )}
        {found.kind === 'ok' && unstored.length === 0 && (
          <p className="rounded-2xl border border-border bg-background p-6 text-sm text-muted-foreground">
            No agent has read a website yet. Ask a market or competitor question in Research.
          </p>
        )}
        {outcome(true)}
        {unstored.length > 0 && (
          <div className="overflow-x-auto rounded-2xl border border-border bg-background shadow-xs" tabIndex={0} role="region" aria-label="Agent websites table, scrolls sideways on small screens">
            <table className="w-full min-w-[760px] border-collapse text-sm">
              <caption className="sr-only">Websites read by agents during research runs</caption>
              <thead>
                <tr className="border-b border-border bg-canvas-tint text-left">
                  <th scope="col" className="p-3 font-semibold">Page</th>
                  <th scope="col" className="p-3 font-semibold">Read by</th>
                  <th scope="col" className="p-3 font-semibold">Result</th>
                  <th scope="col" className="p-3 font-semibold"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {unstored.map((w) => (
                  <tr key={w.url} className="border-b border-border align-top last:border-b-0">
                    <th scope="row" className="max-w-xs p-3 text-left font-normal">
                      <PageLink url={w.url}>{clip(w.title || w.domain, 90)}</PageLink>
                      <span className="block text-xs text-muted-foreground">{`${w.domain}, ${tierLabel(w.trust_tier).toLowerCase()}`}</span>
                    </th>
                    <td className="max-w-56 p-3">
                      {w.agent}
                      <span className="block text-xs text-muted-foreground">
                        {`${fmtDate(w.retrieved_at)}${w.conversation ? `, in "${clip(w.conversation, 40)}"` : ''}`}
                      </span>
                    </td>
                    <td className="max-w-64 p-3">
                      {w.findings > 0 ? `${w.findings} ${w.findings === 1 ? 'finding' : 'findings'}` : 'Read, not used'}
                      {w.findings === 0 && w.skipped_reason && <span className="block text-xs text-muted-foreground">{clip(w.skipped_reason, 110)}</span>}
                    </td>
                    <td className="p-3 text-right">
                      {w.source_id ? <Badge variant="outline">Stored</Badge> : (
                        <Button variant="outline" disabled={busy} aria-label={`Store ${w.domain}`}
                          onClick={() => store({ url: w.url, line: w.vehicle_line ?? undefined, market: w.market ?? undefined, trust_tier: w.trust_tier ?? undefined }, true)}>
                          Store page
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
