import { ArrowUpRight, CheckCircle, DownloadSimple, FileText, UploadSimple } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { useWorkspace } from '../context'
import { composite, dateLabel, downloadFile, scopeKey, statusNames, tier, uid } from '../data'
import type { Metric, Requirement, Source, Status, Weights } from '../data'
import { Badge, Button, Dialog } from './ui'

export function SourceDialog({ source, close }: { source: Source | null; close: () => void }) {
  const { workspace, openRequirement } = useWorkspace()
  return <Dialog open={!!source} onOpenChange={open => { if (!open) close() }} title={source?.name || 'Evidence'} description={source?.uploaded ? 'Locally added source. Parsing has not been run.' : 'Illustrative evidence, with its source locator and linked requirements.'}>
    {source && <div className="dialog-body"><div className="source-detail-meta"><Badge tone={source.level === 'Unverified' ? 'warning' : 'neutral'}>{source.uploaded ? 'Not parsed' : `Demo ${source.level.toLowerCase()}`}</Badge><span>{source.family}</span></div><dl className="detail-list"><div><dt>Locator</dt><dd>{source.locator}</dd></div><div><dt>Added</dt><dd>{dateLabel(source.addedAt)}</dd></div>{source.bytes != null && <div><dt>File size</dt><dd>{(source.bytes / 1024).toFixed(1)} KB</dd></div>}</dl><h3>{source.uploaded ? 'Local preview' : 'Illustrative source excerpt'}</h3><blockquote className="evidence-quote">{source.excerpt}</blockquote><h3>Linked requirements</h3>{workspace.requirements.filter(r => r.sourceIds.includes(source.id)).length ? <div className="linked-requirements">{workspace.requirements.filter(r => r.sourceIds.includes(source.id)).map(r => <button key={r.id} onClick={() => { close(); openRequirement(r) }}>{r.id}: {r.title}<ArrowUpRight size={16} /></button>)}</div> : <p>No requirements are linked to this source yet.</p>}</div>}
  </Dialog>
}

export function RequirementDialog({ requirement, close }: { requirement: Requirement; close: () => void }) {
  const { workspace, mutate, openSource, notify } = useWorkspace()
  const [draft, setDraft] = useState(requirement), [reason, setReason] = useState(''), [error, setError] = useState(''), [editScores, setEditScores] = useState(false)
  const form = useRef<HTMLFormElement>(null)
  const score = composite(draft, workspace.weights)
  const save = (status: Status = draft.status) => {
    if (!form.current?.reportValidity()) return
    if (reason.trim().length < 3) { setError('Add a reason of at least 3 characters. Every decision needs context.'); return }
    const value = { ...draft, status, updatedAt: new Date().toISOString() }
    mutate(status !== requirement.status ? `${requirement.title} moved to ${statusNames[status]}` : `${requirement.title} edited`, reason.trim(), s => ({ ...s, requirements: s.requirements.map(r => r.id === value.id ? value : r) }))
    close(); notify(status === 'tracked' ? 'Requirement approved and tracked.' : 'Your decision and reason were saved.')
  }
  return <Dialog open onOpenChange={open => { if (!open) close() }} title={requirement.title} description={`${requirement.id} · ${requirement.domain} · ${requirement.line} · ${requirement.market}`} wide>
    <form ref={form} className="dialog-body" onSubmit={e => { e.preventDefault(); save() }}><div className="requirement-summary"><Badge tone={requirement.status === 'tracked' ? 'success' : 'blue'}>{statusNames[requirement.status]}</Badge><span><strong>{score.toFixed(2)}</strong> {tier(score)}</span><span><strong>{requirement.confidence}%</strong> confidence</span></div>
      <label htmlFor="requirement-title">Title</label><input id="requirement-title" value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} required maxLength={160} />
      <label htmlFor="requirement-description">Customer need</label><textarea id="requirement-description" value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} required rows={3} />
      <label htmlFor="requirement-metric">Metric or successor target</label><input id="requirement-metric" value={draft.metric} onChange={e => setDraft({ ...draft, metric: e.target.value })} required />
      <label htmlFor="requirement-acceptance">Acceptance criteria</label><textarea id="requirement-acceptance" value={draft.acceptance} onChange={e => setDraft({ ...draft, acceptance: e.target.value })} required rows={2} />
      <div className="detail-section"><div className="section-heading"><h3>An explainable priority.</h3><Button type="button" size="small" variant="ghost" onClick={() => setEditScores(!editScores)}>{editScores ? 'Hide score controls' : 'Edit component scores'}</Button></div><div className="score-breakdown">{([{ key: 'relevance', label: 'Customer relevance' }, { key: 'business', label: 'Business signal' }, { key: 'fit', label: 'Strategic fit' }, { key: 'effort', label: 'Effort proxy' }] as const).map(item => <div key={item.key}><label htmlFor={`score-${item.key}`}>{item.label}<strong>{draft[item.key]} / 100</strong></label>{editScores ? <input id={`score-${item.key}`} type="range" min={0} max={100} value={draft[item.key]} onChange={e => setDraft({ ...draft, [item.key]: Number(e.target.value) })} /> : <div className="score-track"><span style={{ width: `${draft[item.key]}%` }} /></div>}<small>{workspace.weights[item.key]}% weight{item.key === 'effort' ? ' (subtracted)' : ''}</small></div>)}</div></div>
      <div className="detail-section"><h3>Evidence behind the requirement.</h3><div className="citation-row">{requirement.sourceIds.map(id => { const source = workspace.sources.find(s => s.id === id); return source ? <button type="button" key={id} onClick={() => openSource(source)}><FileText size={16} />{source.name}<ArrowUpRight size={13} /></button> : null })}</div><p className="data-note">{requirement.assumption}</p></div>
      <label htmlFor="decision-reason">Reason for your decision</label><textarea id="decision-reason" value={reason} onChange={e => { setReason(e.target.value); setError('') }} placeholder="Record what changed and why." rows={2} required minLength={3} />{error && <p className="field-error" role="alert">{error}</p>}
      <div className="dialog-actions requirement-actions"><Button type="button" onClick={() => save('tracked')}><CheckCircle size={18} /> Approve & track</Button><Button type="submit" variant="secondary">Save changes</Button><Button type="button" variant="ghost" onClick={() => save('challenged')}>Challenge</Button><Button type="button" variant="ghost" onClick={() => save('rejected')}>Reject</Button></div>
    </form>
  </Dialog>
}

export function TargetDialog({ metric, close }: { metric: Metric; close: () => void }) {
  const { metrics, line, market, mutate, notify } = useWorkspace()
  const [value, setValue] = useState(String(metric.target)), [reason, setReason] = useState(''), [error, setError] = useState('')
  return <Dialog open onOpenChange={open => { if (!open) close() }} title={`Set the ${metric.label.toLowerCase()} target`} description="The baseline remains unchanged. Your successor target and its reason are recorded."><form className="dialog-body" onSubmit={e => { e.preventDefault(); const n = Number(value); if (!value.trim() || !Number.isFinite(n) || n < metric.min || n > metric.max) { setError(`Enter a target between ${metric.min} and ${metric.max} ${metric.unit}.`); return } if (reason.trim().length < 3) { setError('Add a reason of at least 3 characters.'); return } mutate(`${metric.label} target updated`, `${metric.target} → ${n} ${metric.unit}. ${reason.trim()}`, s => ({ ...s, metrics: { ...s.metrics, [scopeKey(line, market)]: metrics.map(m => m.id === metric.id ? { ...m, target: n } : m) } })); close(); notify('Successor target saved with your reason.') }}><div className="target-baseline"><span>Current baseline</span><strong>{metric.baseline} <small>{metric.unit}</small></strong></div><label htmlFor="target-value">Successor target ({metric.unit})</label><input id="target-value" autoFocus type="number" min={metric.min} max={metric.max} step="0.1" value={value} onChange={e => setValue(e.target.value)} required /><label htmlFor="target-reason">Reason for the target</label><textarea id="target-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} required minLength={3} placeholder="What customer need or evidence supports this target?" />{error && <p className="field-error" role="alert">{error}</p>}<div className="dialog-actions"><Button type="submit">Save target</Button></div></form></Dialog>
}

export function WeightsDialog({ close }: { close: () => void }) {
  const { workspace, mutate, notify } = useWorkspace()
  const [weights, setWeights] = useState<Weights>({ ...workspace.weights }), [reason, setReason] = useState(''), [error, setError] = useState('')
  const total = Object.values(weights).reduce((sum, n) => sum + n, 0)
  return <Dialog open onOpenChange={open => { if (!open) close() }} title="Make the priority yours." description="Weights apply to this demo workspace. Earlier score settings remain in the exported decision history."><form className="dialog-body" onSubmit={e => { e.preventDefault(); if (total !== 100) { setError('Weights must add up to 100%.'); return } if (reason.trim().length < 3) { setError('Record a reason for the scoring change.'); return } mutate('Priority weights changed', `${JSON.stringify(workspace.weights)} → ${JSON.stringify(weights)}. ${reason.trim()}`, s => ({ ...s, weights })); close(); notify('Weights saved and all requirement priorities recalculated.') }}>
    {([{ key: 'relevance', label: 'Customer relevance' }, { key: 'business', label: 'Business signal' }, { key: 'fit', label: 'Strategic fit' }, { key: 'effort', label: 'Effort proxy (subtracted)' }] as const).map(item => <div className="weight-field" key={item.key}><label htmlFor={`weight-${item.key}`}>{item.label}</label><div><input id={`weight-${item.key}`} type="range" min={0} max={100} value={weights[item.key]} onChange={e => setWeights({ ...weights, [item.key]: Number(e.target.value) })} /><output htmlFor={`weight-${item.key}`}>{weights[item.key]}%</output></div></div>)}
    <p className={total === 100 ? 'blue-text' : 'field-error'}>Total: {total}% of 100%</p><label htmlFor="weights-reason">Reason for the change</label><textarea id="weights-reason" value={reason} onChange={e => setReason(e.target.value)} rows={2} required minLength={3} />{error && <p role="alert" className="field-error">{error}</p>}<div className="dialog-actions"><Button type="submit" disabled={total !== 100}>Save weights</Button></div>
  </form></Dialog>
}

export function ImportDialog({ close }: { close: () => void }) {
  const { line, market, mutate, notify } = useWorkspace()
  const [file, setFile] = useState<File | null>(null), [family, setFamily] = useState('Customer feedback'), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!file) { setError('Choose a document first.'); return }
    if (file.size > 10 * 1024 * 1024) { setError('Choose a file smaller than 10 MB.'); return }
    if (!/\.(pdf|xlsx?|docx?|pptx?|csv|json|txt)$/i.test(file.name)) { setError('Use PDF, Excel, Word, PowerPoint, CSV, JSON, or plain text.'); return }
    setBusy(true); setError('')
    try {
      const preview = /\.(txt|csv|json)$/i.test(file.name) ? (await file.text()).slice(0, 15000) : 'This binary document has been registered locally. Its contents have not been parsed. Connect the ingestion backend to extract citable pages, rows, or cells.'
      const source: Source = { id: uid(), name: file.name, family, locator: 'Local upload, parsing pending', excerpt: preview || 'This file is empty.', level: 'Unverified', line, market, addedAt: new Date().toISOString(), uploaded: true, bytes: file.size }
      mutate('Document added locally', `${file.name} registered in ${line} / ${market}. No automated parsing has run.`, s => ({ ...s, sources: [source, ...s.sources] })); close(); notify('Document registered locally. Parsing has not been run.')
    } catch { setError('The file could not be read. Choose another document.'); setBusy(false) }
  }
  return <Dialog open onOpenChange={open => { if (!open && !busy) close() }} title="Add evidence to your programme." description="Files stay local. PDF, Office, CSV, JSON, and text are supported for registration; text files include a preview."><form className="dialog-body" onSubmit={submit}><label htmlFor="evidence-file">Document (up to 10 MB)</label><div className="upload-area"><UploadSimple size={28} /><input id="evidence-file" type="file" accept=".pdf,.xls,.xlsx,.doc,.docx,.ppt,.pptx,.csv,.json,.txt" disabled={busy} onChange={e => { setFile(e.target.files?.[0] || null); setError('') }} />{file && <p>{file.name} · {(file.size / 1024).toFixed(1)} KB</p>}</div><label htmlFor="source-family">Input family</label><select id="source-family" value={family} onChange={e => setFamily(e.target.value)}>{['Customer feedback', 'Customer study', 'Product catalog', 'Sales', 'Competitor research', 'Market research', 'Social media'].map(f => <option key={f}>{f}</option>)}</select>{error && <p className="field-error" role="alert">{error}</p>}<p className="data-note">No findings or evidence grades are inferred from the filename. Added documents are unverified until an ingestion service processes them.</p><div className="dialog-actions"><Button type="submit" disabled={!file || busy}>{busy ? 'Reading document...' : 'Add document'}</Button></div></form></Dialog>
}

export function SettingsDialog({ close, reset }: { close: () => void; reset: () => void }) {
  const { workspace, notify } = useWorkspace()
  return <Dialog open onOpenChange={open => { if (!open) close() }} title="Your demo workspace" description="The programme is stored in this browser. No data is sent to BMW, Supabase, or an AI provider."><div className="dialog-body"><h3>Keep a copy of your decisions.</h3><p>Export your targets, requirements, source previews, research reviews, weights, and decision history as JSON.</p><Button variant="secondary" onClick={() => { downloadFile('bmw-programme-workspace.json', JSON.stringify(workspace, null, 2), 'application/json'); notify('Workspace backup downloaded.') }}><DownloadSimple size={18} /> Download workspace</Button><div className="detail-section"><h3>Start again with the sample programme.</h3><p>Resetting removes the edits and documents saved in this browser. Export a copy first if you need them.</p><Button variant="danger" onClick={reset}>Reset demo workspace</Button></div></div></Dialog>
}
