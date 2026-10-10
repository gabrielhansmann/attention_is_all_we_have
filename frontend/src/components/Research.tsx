import { ArrowRight, Check, CheckCircle, MagnifyingGlass, PencilSimple, Plus, Sparkle, X } from '@phosphor-icons/react'
import { lazy, Suspense, useState } from 'react'
import { useWorkspace } from '../context'
import { createResearch, dateLabel, uid } from '../data'
import type { Requirement, ResearchRun } from '../data'
import { liveEnabled } from '../lib/live'
import { Badge, Button, Dialog, Empty } from './ui'

const LiveResearch = lazy(() => import('../features/research/LiveResearch').then(module => ({ default: module.LiveResearch })))

export function Research() {
  const { workspace, line, market, mutate, openSource, openRequirement, notify } = useWorkspace()
  const [query, setQuery] = useState(''), [selected, setSelected] = useState(''), [note, setNote] = useState(''), [error, setError] = useState('')
  const [live, setLive] = useState(false)
  const [edit, setEdit] = useState<{ index: number; summary: string } | null>(null)
  const [rejection, setRejection] = useState<{ run: string; index: number } | null>(null)
  const runs = workspace.runs.filter(r => r.line === line && r.market === market)
  const run = runs.find(r => r.id === selected) || runs[0]
  const updateRun = (value: ResearchRun) => (s: typeof workspace) => ({ ...s, runs: s.runs.map(r => r.id === value.id ? value : r) })
  const start = (event: React.FormEvent) => {
    event.preventDefault()
    if (query.trim().length < 5) { setError('Enter a research question with at least 5 characters.'); return }
    const created = createResearch(query.trim(), line, market)
    mutate('Research plan started', `Demo question: ${query.trim()}`, s => ({ ...s, runs: [created, ...s.runs] }))
    setSelected(created.id); setQuery(''); setNote(''); setError('')
  }
  const finish = (value: ResearchRun) => {
    const lastAccepted = value.steps.at(-1)?.status === 'accepted'
    const draft: Requirement | undefined = lastAccepted ? {
      id: `D-${uid().slice(0, 6).toUpperCase()}`, title: value.query, description: `Customer-facing requirement proposed from the accepted demo research: ${value.query}`,
      domain: 'Usability', line, market, status: 'draft', metric: 'Successor target to be set by the PM', acceptance: 'Define a defensible metric, agree on the validation protocol, and corroborate the demo evidence before approval.',
      sourceIds: [...new Set(value.steps.filter(s => s.status === 'accepted').flatMap(s => s.sourceIds))], confidence: value.steps.some(s => s.status === 'rejected') ? 30 : 55,
      relevance: 65, business: 50, fit: 65, effort: 50, assumption: `Created from demo fixtures, without live web research.${value.steps.some(s => s.status === 'rejected') ? ' Coverage gap: a research contribution was rejected by the PM.' : ''}`, updatedAt: new Date().toISOString(),
    } : undefined
    mutate('Research completed', 'The final result contains only accepted demo contributions.', s => ({ ...s, runs: s.runs.map(r => r.id === value.id ? { ...value, status: 'completed', draftId: draft?.id } : r), requirements: draft ? [draft, ...s.requirements] : s.requirements }), 'Demo orchestrator')
    notify(draft ? 'Research complete. A draft requirement is ready for your review.' : 'Research complete with a documented coverage gap.')
  }
  const accept = (index: number) => {
    if (!run || !note.trim()) { setError('Add a review reason before accepting a step.'); return }
    const value = { ...run, steps: run.steps.map((s, i) => i === index ? { ...s, status: 'accepted' as const } : i === index + 1 ? { ...s, status: 'awaiting_review' as const } : s), notes: [...run.notes, `You accepted ${run.steps[index].name}: ${note.trim()}`] }
    mutate(`${run.steps[index].name} accepted`, note.trim(), updateRun(value))
    setNote(''); setError('')
    if (index === run.steps.length - 1) finish(value)
  }
  const retry = (index: number) => {
    if (!run || !note.trim()) { setError('Describe what the agent should reconsider.'); return }
    const value = { ...run, steps: run.steps.map((s, i) => i === index ? { ...s, summary: `${s.summary.split('\n\nPM steering:')[0]}\n\nPM steering: ${note.trim()}\nThis demo retry retains the fixture evidence. New evidence must be collected by the live agent before changing the claim.` } : s), notes: [...run.notes, `You requested a retry: ${note.trim()}`] }
    mutate(`${run.steps[index].name} retry requested`, note.trim(), updateRun(value)); setNote(''); setError(''); notify('Steering recorded. The demo retains its cited fixture evidence.')
  }
  const reject = (index: number) => {
    if (!run || !note.trim()) { setError('Explain why this contribution should be rejected.'); return }
    mutate(`${run.steps[index].name} rejected`, note.trim(), updateRun({ ...run, steps: run.steps.map((s, i) => i === index ? { ...s, status: 'rejected' } : s), notes: [...run.notes, `You rejected ${run.steps[index].name}: ${note.trim()}`] }))
    setRejection({ run: run.id, index }); setNote(''); setError('')
  }
  const continueAfterReject = (abort: boolean) => {
    if (!rejection) return
    const target = workspace.runs.find(r => r.id === rejection.run)!
    const value = { ...target, status: abort ? 'aborted' as const : 'active' as const, steps: target.steps.map((s, i) => !abort && i === rejection.index + 1 ? { ...s, status: 'awaiting_review' as const } : s) }
    mutate(abort ? 'Research aborted' : 'Research continued with a coverage gap', abort ? 'PM aborted the run after rejecting a contribution.' : `${target.steps[rejection.index].name} is excluded from the final result.`, updateRun(value))
    if (!abort && rejection.index === target.steps.length - 1) finish(value)
    setRejection(null)
  }
  const unresolvedIndex = run?.steps.findIndex((step, index) => step.status === 'rejected' && (!run.steps[index + 1] || run.steps[index + 1].status === 'planned')) ?? -1
  const pendingRejected = run?.status === 'active' && !run.steps.some(s => s.status === 'awaiting_review') && unresolvedIndex >= 0
  if (live) return <>
    <div className="page-heading"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h1>Ask. Review. Decide.</h1><p>One question, a visible plan, and your approval at every step.</p></div><Badge tone="blue">Live planner</Badge></div>
    {liveEnabled && <div className="evidence-mode-controls"><Button variant={live ? 'secondary' : 'primary'} aria-pressed={!live} onClick={() => setLive(false)}>Demo walkthrough</Button><Button variant={live ? 'primary' : 'secondary'} aria-pressed={live} onClick={() => setLive(true)}>Live planner (backend)</Button></div>}
    <section className="live-research-section"><Suspense fallback={<p role="status">Loading the live planner...</p>}><LiveResearch /></Suspense></section>
  </>
  return <>
    <div className="page-heading"><div><p className="eyebrow">RESEARCH WORKSPACE</p><h1>Ask. Review. Decide.</h1><p>One question, a visible plan, and your approval at every step.</p></div><Badge tone="blue">Guided demo</Badge></div>
    {liveEnabled && <div className="evidence-mode-controls"><Button variant={live ? 'secondary' : 'primary'} aria-pressed={!live} onClick={() => setLive(false)}>Demo walkthrough</Button><Button variant={live ? 'primary' : 'secondary'} aria-pressed={live} onClick={() => setLive(true)}>Live planner (backend)</Button></div>}
    <div className="notice"><Sparkle size={20} /><p>This research flow uses illustrative fixtures. It makes no live AI or web calls. Each accepted step starts the next; the final result appears after review.</p></div>
    <form className="research-composer" onSubmit={start}><label htmlFor="research-question">What would you like to explore?</label><div className="composer-row"><input id="research-question" value={query} maxLength={500} onChange={e => { setQuery(e.target.value); setError('') }} placeholder="What should we improve about cabin comfort?" /><Button type="submit" disabled={query.trim().length < 5}>Start research <ArrowRight size={18} /></Button></div><div className="suggested-questions">{['Improve cabin comfort', 'Close the charging gap', 'Simplify climate controls'].map(q => <button type="button" key={q} onClick={() => setQuery(q)}>{q}<Plus size={13} /></button>)}</div></form>
    {error && <p className="field-error" role="alert">{error}</p>}
    {runs.length > 0 && <div className="research-history"><label htmlFor="research-history">Research history</label><select id="research-history" value={run?.id} onChange={e => { setSelected(e.target.value); setError(''); setNote('') }}>{runs.map(r => <option key={r.id} value={r.id}>{r.query} ({r.status})</option>)}</select></div>}
    {!run ? <Empty title="A question is a good place to start">Explore a customer need or product aspect. You will review the evidence before it becomes a requirement.</Empty> : <section className="research-run"><div className="section-heading"><div><h2>{run.query}</h2><p>Started {dateLabel(run.createdAt)}</p></div><Badge tone={run.status === 'completed' ? 'success' : run.status === 'aborted' ? 'warning' : 'blue'}>{run.status === 'completed' ? 'Complete' : run.status === 'aborted' ? 'Aborted' : 'Awaiting your review'}</Badge></div>
      <div className="plan-strip" aria-label="Research plan">{run.steps.map((s, i) => <div key={s.name} className={`plan-step plan-${s.status}`}><span>{s.status === 'accepted' ? <Check size={16} /> : s.status === 'rejected' ? <X size={16} /> : i + 1}</span><div><strong>{s.name}</strong><small>{s.status.replaceAll('_', ' ')}</small></div></div>)}</div>
      {run.steps.map((step, index) => <article className={`step-card step-${step.status}`} key={`${run.id}-${step.name}`}><div className="step-heading"><span className="step-icon">{step.status === 'accepted' ? <CheckCircle size={22} /> : <MagnifyingGlass size={22} />}</span><div><h3>{step.name}</h3><p>{step.reason}</p></div><Badge tone={step.status === 'accepted' ? 'success' : step.status === 'rejected' ? 'warning' : step.status === 'awaiting_review' ? 'blue' : 'neutral'}>{step.status === 'awaiting_review' ? 'Review needed' : step.status[0].toUpperCase() + step.status.slice(1)}</Badge></div>
        {step.status !== 'planned' ? <><p className="step-summary">{step.summary}</p><div className="citation-row">{step.sourceIds.map(id => { const source = workspace.sources.find(s => s.id === id); return source ? <button key={id} onClick={() => openSource(source)}>{source.name} <ArrowRight size={13} /></button> : null })}</div></> : <p className="planned-note">{run.status === 'aborted' ? 'This step did not run because the research was aborted.' : 'This step begins after the previous contribution is accepted.'}</p>}
        {step.status === 'awaiting_review' && run.status === 'active' && <div className="step-review"><label htmlFor={`review-note-${index}`}>Your review reason or steering note</label><textarea id={`review-note-${index}`} rows={2} value={note} onChange={e => { setNote(e.target.value); setError('') }} placeholder="Explain the decision or what should change." /><div className="review-actions"><Button onClick={() => accept(index)}><Check size={18} /> Accept & continue</Button><Button variant="secondary" onClick={() => { setEdit({ index, summary: step.summary }); setError('') }}><PencilSimple size={17} /> Edit</Button><Button variant="secondary" onClick={() => retry(index)}>Retry</Button><Button variant="ghost" onClick={() => reject(index)}>Reject</Button></div></div>}
      </article>)}
      {pendingRejected && <div className="notice"><p>A rejected contribution needs a decision before this run continues.</p><Button variant="secondary" onClick={() => setRejection({ run: run.id, index: unresolvedIndex })}>Resolve rejection</Button></div>}
      {run.notes.length > 0 && <div className="run-notes"><h3>Your decisions</h3>{run.notes.map((message, i) => <p key={i}>{message}</p>)}</div>}
      {run.status === 'completed' && <div className="final-result"><CheckCircle size={28} /><div><h2>Research reviewed. Direction recorded.</h2><p>{run.draftId ? 'A draft requirement is in your portfolio. Set a defensible target and review the evidence before tracking it.' : 'No requirement was drafted because the drafting contribution was rejected.'}</p>{run.draftId && <Button variant="secondary" onClick={() => { const draft = workspace.requirements.find(r => r.id === run.draftId); if (draft) openRequirement(draft) }}>Review draft <ArrowRight size={16} /></Button>}</div></div>}
    </section>}
    <Dialog open={!!edit} onOpenChange={open => { if (!open) setEdit(null) }} title="Edit the contribution" description="The summary changes only when you save. Your reason is recorded.">
      <form onSubmit={e => { e.preventDefault(); if (!edit || !run) return; if (!note.trim() || !edit.summary.trim()) { setError('Provide both a summary and a reason.'); return } mutate(`${run.steps[edit.index].name} edited`, note.trim(), updateRun({ ...run, steps: run.steps.map((s, i) => i === edit.index ? { ...s, summary: edit.summary.trim() } : s), notes: [...run.notes, `You edited ${run.steps[edit.index].name}: ${note.trim()}`] })); setEdit(null); setNote(''); setError('') }} className="dialog-body"><label htmlFor="step-summary">Summary</label><textarea id="step-summary" rows={7} value={edit?.summary || ''} onChange={e => setEdit(value => value ? { ...value, summary: e.target.value } : null)} required /><label htmlFor="edit-reason">Reason</label><input id="edit-reason" value={note} onChange={e => setNote(e.target.value)} required />{error && <p role="alert" className="field-error">{error}</p>}<div className="dialog-actions"><Button type="submit">Save contribution</Button></div></form>
    </Dialog>
    <Dialog open={!!rejection} onOpenChange={open => { if (!open) setRejection(null) }} title="How should the research proceed?" description="A rejected contribution is excluded. Continuing records a coverage gap on the resulting draft."><div className="dialog-body"><p>Continue with the remaining evidence, or stop this run and start again with a different question.</p><div className="dialog-actions"><Button variant="secondary" onClick={() => continueAfterReject(true)}>Abort research</Button><Button onClick={() => continueAfterReject(false)}>Continue with gap</Button></div></div></Dialog>
  </>
}
