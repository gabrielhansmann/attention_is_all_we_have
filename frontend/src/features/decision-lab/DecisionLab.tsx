import { useState } from 'react'
import { ArrowDown, ArrowRight, ArrowUp, ArrowUpRight, DownloadSimple, Flask, SlidersHorizontal } from '@phosphor-icons/react'
import { useWorkspace } from '../../context'
import { downloadFile, lineNames, marketNames, statusNames, tier } from '../../data'
import type { Requirement, Weights } from '../../data'
import { Badge, Button, Dialog, Empty } from '../../components/ui'
import { compareScenario, lenses, rebalanceWeight, sameWeights, scenarioBrief, weightFields } from './model'
import './decision-lab.css'

const signed = (value: number, digits = 4) => `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`
const barStyle = (score: number) => ({ left: `${50 + Math.min(0, score) * 50}%`, width: `${Math.abs(score) * 50}%` })

function ScorePlot({ before, after, title }: { before: number; after: number; title: string }) {
  return <div className="lab-score-plot" role="img" aria-label={`${title}: saved score ${before.toFixed(4)}, scenario score ${after.toFixed(4)}. Scores range from minus one to one.`}>
    <div className="lab-plot-row"><span>Saved</span><div className="lab-plot-track"><span className="lab-plot-bar lab-plot-saved" style={barStyle(before)} /></div><strong>{before.toFixed(2)}</strong></div>
    <div className="lab-plot-row"><span>Scenario</span><div className="lab-plot-track"><span className="lab-plot-bar" style={barStyle(after)} /></div><strong>{after.toFixed(2)}</strong></div>
    <div className="lab-plot-axis" aria-hidden="true"><span>-1</span><span>0</span><span>1</span></div>
  </div>
}

function ScoreExplanation({ requirement, weights }: { requirement: Requirement; weights: Weights }) {
  const { workspace, openSource } = useWorkspace()
  return <details className="lab-explanation">
    <summary>Explain score and evidence</summary>
    <div className="lab-explanation-body">
      <div className="table-scroll" role="region" aria-label={`Scenario score calculation for ${requirement.title}`} tabIndex={0}>
        <table className="lab-calculation"><thead><tr><th scope="col">Component</th><th scope="col">Value / 100</th><th scope="col">Weight</th><th scope="col">Contribution</th></tr></thead><tbody>
          {weightFields.map(field => <tr key={field.key}><th scope="row">{field.label}</th><td>{requirement[field.key]}</td><td>{weights[field.key]}%</td><td>{signed(requirement[field.key] * weights[field.key] / 10000 * (field.key === 'effort' ? -1 : 1))}</td></tr>)}
        </tbody></table>
      </div>
      <p className="lab-assumption"><strong>Assumption</strong> {requirement.assumption}</p>
      <div className="lab-source-links">{requirement.sourceIds.length ? requirement.sourceIds.map(id => {
        const source = workspace.sources.find(item => item.id === id)
        return source ? <button key={id} onClick={() => openSource(source)}>{source.name}<span>{source.locator}</span><ArrowUpRight size={15} /></button> : <p key={id}>Source unavailable: {id}</p>
      }) : <p>No sources attached. Collect evidence before a commitment.</p>}</div>
    </div>
  </details>
}

export function DecisionLab() {
  const { workspace, requirements, line, market, mutate, notify, navigate, openRequirement } = useWorkspace()
  const [preview, setPreview] = useState<Weights>({ ...workspace.weights })
  const [lensName, setLensName] = useState('Saved weights')
  const [slots, setSlots] = useState(3)
  const [saving, setSaving] = useState(false), [reason, setReason] = useState(''), [error, setError] = useState('')
  const rows = compareScenario(requirements, workspace.weights, preview, slots)
  const limit = Math.min(slots, rows.length)
  const entering = rows.filter(row => row.change === 'Enters'), leaving = rows.filter(row => row.change === 'Leaves')
  const changed = !sameWeights(workspace.weights, preview)
  const selected = lenses.find(lens => sameWeights(lens.weights, preview))?.id
  const thin = rows.filter(row => row.shortlisted && (row.requirement.confidence < 60 || row.requirement.sourceIds.length < 2))
  const summary = `${entering.length} enters, ${leaving.length} leaves, ${limit - entering.length} stays in the top ${limit}.`
  const exportBrief = () => {
    downloadFile(`decision-lab-${line}-${market}.md`, scenarioBrief(requirements, workspace.sources, workspace.weights, preview, slots, line, market), 'text/markdown;charset=utf-8')
    notify('Scenario brief downloaded with score comparisons, sources, and assumptions.')
  }
  const save = () => {
    if (reason.trim().length < 3) { setError('Record a reason of at least 3 characters.'); return }
    if (!changed) { setSaving(false); return }
    mutate('Decision Lab weights applied', `${lensName}. Saved weights: ${JSON.stringify(workspace.weights)}. New weights: ${JSON.stringify(preview)}. ${line} / ${market}, top ${limit}: entering ${entering.map(row => row.requirement.id).join(', ') || 'none'}; leaving ${leaving.map(row => row.requirement.id).join(', ') || 'none'}. Weights apply across the demo workspace. Reason: ${reason.trim()}`, state => ({ ...state, weights: { ...preview } }))
    setSaving(false); setReason(''); setError('')
    notify('Scenario weights saved. All demo requirement scores have been recalculated.')
  }

  return <>
    <section className="hero-band lab-hero">
      <div><p className="eyebrow">DECISION LAB</p><h1>Test the <span className="lab-heading-word">trade-offs.</span></h1><p className="hero-description">Change the priorities. See what moves before you make the call.</p>
        <div className="hero-scope"><span>{lineNames[line]} / {marketNames[market]}</span><span>Illustrative scenarios</span></div></div>
      <Flask size={64} weight="light" className="lab-hero-icon" aria-hidden="true" />
    </section>

    <div className="lab-workspace">
      <section className="lab-controls" aria-labelledby="lab-controls-title">
        <div className="section-heading"><h2 id="lab-controls-title">Choose a lens.</h2><SlidersHorizontal size={20} aria-hidden="true" /></div>
        <p className="lab-help">These example strategies change weights, while the underlying evidence stays the same.</p>
        <div className="lab-lenses">{lenses.map(lens => <button key={lens.id} className={`lab-lens ${selected === lens.id ? 'lab-lens-selected' : ''}`} aria-pressed={selected === lens.id} onClick={() => { setPreview({ ...lens.weights }); setLensName(lens.name) }}><strong>{lens.name}</strong><span>{lens.description}</span></button>)}</div>
        <div className="lab-weight-heading"><h3>Fine-tune the weights.</h3><span>100% total</span></div>
        {weightFields.map(field => <div className="weight-field lab-weight" key={field.key}>
          <label htmlFor={`lab-weight-${field.key}`}>{field.label}</label>
          <div><input id={`lab-weight-${field.key}`} type="range" min={0} max={100} step={1} value={preview[field.key]} aria-describedby={`lab-help-${field.key}`} onChange={event => { setPreview(rebalanceWeight(preview, field.key, Number(event.target.value))); setLensName('Custom lens') }} /><output htmlFor={`lab-weight-${field.key}`}>{preview[field.key]}%</output></div>
          <p id={`lab-help-${field.key}`}>{field.help}</p>
        </div>)}
        <p className="lab-help lab-rebalance-note">Other weights adjust proportionally to keep the total at 100%. Effort is subtracted. Confidence stays separate.</p>
        <Button variant="secondary" className="lab-reset" onClick={() => { setPreview({ ...workspace.weights }); setLensName('Saved weights') }} disabled={!changed}>Reset to saved weights</Button>
      </section>

      <section className="lab-results" aria-labelledby="lab-results-title">
        <div className="lab-results-heading"><div><p className="eyebrow">{lensName.toUpperCase()}</p><h2 id="lab-results-title">What makes the shortlist?</h2><p>Compared with your saved priorities in this scope.</p></div><div className="lab-slots"><label htmlFor="lab-shortlist-size">Shortlist size</label><select id="lab-shortlist-size" value={limit} disabled={!rows.length} onChange={event => setSlots(Number(event.target.value))}>{rows.length ? Array.from({ length: Math.min(5, rows.length) }, (_, i) => <option key={i + 1} value={i + 1}>Top {i + 1}</option>) : <option value={0}>No requirements</option>}</select></div></div>
        {rows.length > 0 && <>
          <div className="lab-impact" role="status" aria-live="polite" aria-atomic="true"><span><strong>{entering.length}</strong> enters</span><span><strong>{leaving.length}</strong> leaves</span><span><strong>{limit - entering.length}</strong> stays</span><p>{changed ? 'Scenario preview. Your saved weights have not changed.' : 'Matches your saved weights.'}</p></div>
          <div className="lab-evidence-note"><p><strong>Keep evidence in view.</strong> {thin.length ? `${thin.length} shortlisted requirement${thin.length === 1 ? ' needs' : 's need'} more evidence.` : 'A shortlist is a direction to review, not an engineering commitment.'}</p><p>Rejected requirements are excluded. Challenged requirements remain visible for review.</p></div>
          <ol className="lab-ranking" aria-label="Scenario ranking">{rows.map(row => <li key={row.requirement.id} className={`lab-ranked-item ${row.shortlisted ? 'lab-shortlisted' : ''}`} data-requirement-id={row.requirement.id}>
            <div className="lab-rank"><strong aria-label={`Scenario rank ${row.rank}`}>{String(row.rank).padStart(2, '0')}</strong><span>was {row.savedRank}</span></div>
            <div className="lab-ranked-content"><div className="lab-row-heading"><div><span className="cell-caption">{row.requirement.id} / {row.requirement.domain}</span><button className="table-title" onClick={() => openRequirement(row.requirement)}>{row.requirement.title}<ArrowUpRight size={15} /></button></div><Badge tone={row.change === 'Enters' ? 'blue' : row.change === 'Leaves' ? 'warning' : 'neutral'}>{row.change === 'Outside' ? 'Outside shortlist' : row.change}</Badge></div>
              <div className="lab-row-metrics"><ScorePlot before={row.savedScore} after={row.score} title={row.requirement.title} /><div className="lab-row-evidence"><strong>{row.requirement.confidence}% confidence</strong><span>{row.requirement.sourceIds.length} source{row.requirement.sourceIds.length === 1 ? '' : 's'} / {statusNames[row.requirement.status]}</span><span>{tier(row.score)}</span>{(row.requirement.confidence < 60 || row.requirement.sourceIds.length < 2) && <Badge tone="warning">Thin evidence</Badge>}</div></div>
              <div className="lab-row-foot"><span className={row.movement ? 'lab-movement' : ''}>{row.movement > 0 ? <ArrowUp size={14} aria-hidden="true" /> : row.movement < 0 ? <ArrowDown size={14} aria-hidden="true" /> : <ArrowRight size={14} aria-hidden="true" />}{row.movement ? `${Math.abs(row.movement)} place${Math.abs(row.movement) === 1 ? '' : 's'} ${row.movement > 0 ? 'up' : 'down'}` : 'Same rank'}</span><span>Top {limit} in {row.lensCount}/{lenses.length} example lenses</span></div>
              <ScoreExplanation requirement={row.requirement} weights={preview} />
            </div>
          </li>)}</ol>
          <p className="lab-help lab-lens-note">Example-lens counts compare the four presets at the selected shortlist size. They describe sensitivity to priorities, not probability or evidence quality. Equal scores sort by requirement ID.</p>
          <div className="lab-save-panel"><div><h3>Keep the reasoning with the decision.</h3><p>A brief captures this comparison and the evidence behind it. Saving applies weights across the demo workspace.</p></div><div className="lab-actions"><Button variant="secondary" onClick={exportBrief}><DownloadSimple size={18} /> Export scenario brief</Button><Button disabled={!changed} onClick={() => { setError(''); setSaving(true) }}>Apply scenario weights <ArrowRight size={18} /></Button></div></div>
        </>}
        {!rows.length && <Empty title="No active requirements in this scope">Choose another vehicle line or market, or create a draft through Research.</Empty>}
        <p className="data-note">All scores, evidence, and strategies here are illustrative demo data. This lab does not run agents or assess engineering feasibility.</p>
        <Button variant="ghost" onClick={() => navigate('requirements')}>Back to requirements <ArrowRight size={16} /></Button>
      </section>
    </div>

    <Dialog open={saving} onOpenChange={setSaving} title="Apply this scenario?" description="These weights will recalculate every requirement in the local demo workspace, across all vehicle lines and markets.">
      <form className="dialog-body" onSubmit={event => { event.preventDefault(); save() }}><p>{summary}</p><p className="lab-help">Requirements keep their status, source evidence, and confidence. The weight comparison and your reason will be recorded in decision history.</p><label htmlFor="lab-save-reason">Reason for applying this scenario</label><textarea id="lab-save-reason" rows={3} required minLength={3} value={reason} onChange={event => { setReason(event.target.value); setError('') }} />{error && <p className="field-error" role="alert">{error}</p>}<div className="dialog-actions"><Button type="button" variant="secondary" onClick={() => setSaving(false)}>Keep exploring</Button><Button type="submit">Save scenario weights</Button></div></form>
    </Dialog>
  </>
}
