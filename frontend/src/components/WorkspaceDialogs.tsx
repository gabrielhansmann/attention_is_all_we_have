import { useState } from 'react'
import { useWorkspace } from '../context'
import { confidenceLabel, formatNumber, statusLabel } from '../data'
import { api, ApiError } from '../lib/api'
import type { StoredRequirement } from '../types/api'
import { Badge, Button, Dialog, Empty } from './ui'

export function RequirementDialog({ requirement: r, close }: { requirement: StoredRequirement; close: () => void }) {
  const { refresh, notify } = useWorkspace()
  const [reason, setReason] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false)
  async function review(status: string) {
    setBusy(true); setError('')
    try {
      await api.reviewRequirement(r.id, status, r.status, reason.trim())
      notify(`Requirement saved as ${statusLabel(status)}.`)
      close()
      try { await refresh() } catch (e) { notify(`Status saved. Refresh the workspace to see it: ${e instanceof ApiError ? e.message : 'Refresh failed.'}`) }
    } catch (e) { setError(e instanceof ApiError ? e.message : 'The review could not be saved.') }
    finally { setBusy(false) }
  }
  return <Dialog open onOpenChange={open => { if (!open && !busy) close() }} title={r.title} description={`${r.code || r.id} / ${statusLabel(r.status)}`} wide><div className="dialog-body">
    <Badge>{r.evidence_level || 'Evidence level not recorded'}</Badge><p>{r.description}</p>
    <dl className="report-facts"><div><dt>Metric</dt><dd>{r.metric || 'Not recorded'}</dd></div><div><dt>Acceptance criteria</dt><dd>{r.acceptance_criteria || 'Not recorded'}</dd></div><div><dt>Score</dt><dd>{r.score === null ? 'Not scored' : formatNumber(r.score)}</dd></div><div><dt>Confidence</dt><dd>{confidenceLabel(r.confidence)}</dd></div></dl>
    {r.score_rationale && <div className="detail-section"><h3>Scoring rationale</h3><p>{r.score_rationale}</p><p className="cell-caption">Weight vector: {r.weight_vector_version}</p></div>}
    {r.assumptions.length > 0 && <div className="detail-section"><h3>Assumptions</h3><ul>{r.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}
    {r.uncertainties.length > 0 && <div className="detail-section"><h3>Uncertainties</h3><ul>{r.uncertainties.map((a, i) => <li key={i}>{a}</li>)}</ul></div>}
    <div className="detail-section"><h3>Cited evidence</h3>{r.citations.length ? r.citations.map(c => <article className="citation-block" key={c.id}><strong>{c.file}</strong><p>{c.locator}</p><blockquote>{c.quote}</blockquote><Badge>{c.evidence_level}</Badge></article>) : <Empty title="No evidence linked">This requirement has no persisted source links.</Empty>}</div>
    {r.allowed_statuses.length > 0 && <div className="detail-section"><h3>Record your decision</h3><label htmlFor="requirement-reason">Review reason</label><textarea id="requirement-reason" rows={3} maxLength={2000} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} /><p className="cell-caption">A reason is required and saved with your identity in the audit trail.</p>{error && <p role="alert" className="error-text">{error}</p>}<div className="dialog-actions">{r.allowed_statuses.map(status => <Button key={status} variant={status === 'rejected' || status === 'superseded' ? 'danger' : 'primary'} disabled={busy || reason.trim().length < 3} onClick={() => { void review(status) }}>{busy ? 'Saving...' : `Move to ${statusLabel(status)}`}</Button>)}</div></div>}
  </div></Dialog>
}
