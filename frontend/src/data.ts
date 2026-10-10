export type Page = 'overview' | 'requirements' | 'research' | 'evidence' | 'reports'
export type Line = 'G60' | 'F70' | 'G70'
export type Market = 'EU' | 'US' | 'CN'
export type Status = 'draft' | 'pm_review' | 'tracked' | 'challenged' | 'rejected'
export type EvidenceLevel = 'Verified' | 'Interpreted' | 'Unverified'
export type Source = {
  id: string; name: string; family: string; locator: string; excerpt: string
  level: EvidenceLevel; market: Market | 'All'; line: Line | 'All'; addedAt: string
  uploaded?: boolean; bytes?: number
}
export type Requirement = {
  id: string; title: string; description: string; domain: string; line: Line; market: Market
  status: Status; metric: string; acceptance: string; sourceIds: string[]; confidence: number
  relevance: number; business: number; fit: number; effort: number; assumption: string; updatedAt: string
}
export type Metric = {
  id: string; label: string; baseline: number; competition: number; target: number; unit: string
  min: number; max: number; lower: boolean; priority: number; sourceId: string; trend: number[]
}
export type Audit = { id: string; title: string; detail: string; actor: string; time: string; line: Line; market: Market }
export type ResearchStep = { name: string; reason: string; status: 'planned' | 'awaiting_review' | 'accepted' | 'rejected'; summary: string; sourceIds: string[] }
export type ResearchRun = {
  id: string; query: string; line: Line; market: Market; createdAt: string
  status: 'active' | 'completed' | 'aborted'; steps: ResearchStep[]; notes: string[]; draftId?: string
}
export type Weights = { relevance: number; business: number; fit: number; effort: number }
export type Workspace = {
  version: 1; sources: Source[]; requirements: Requirement[]; metrics: Record<string, Metric[]>
  audits: Audit[]; runs: ResearchRun[]; weights: Weights
}

export const lineNames: Record<Line, string> = { G60: '5 Series', F70: '1 Series', G70: '7 Series' }
export const marketNames: Record<Market, string> = { EU: 'Europe', US: 'United States', CN: 'China' }
export const statusNames: Record<Status, string> = { draft: 'Draft', pm_review: 'In review', tracked: 'Tracked', challenged: 'Challenged', rejected: 'Rejected' }
export const priorityNames = ['Monitor', 'Consider', 'Important', 'High priority', 'Critical']
export const defaultWeights: Weights = { relevance: 40, business: 25, fit: 15, effort: 20 }
export const storageKey = 'bmw-product-intelligence-v1'
export const scopeKey = (line: Line, market: Market) => `${line}-${market}`
export const uid = () => crypto.randomUUID()
export const composite = (r: Requirement, w: Weights) => (r.relevance * w.relevance + r.business * w.business + r.fit * w.fit - r.effort * w.effort) / 10000
export const tier = (score: number) => score >= 0.65 ? 'Must-have' : score >= 0.4 ? 'Should-have' : 'Watch-list'
export const formatNumber = (value: number) => new Intl.NumberFormat('en', { maximumFractionDigits: 1 }).format(value)
export const dateLabel = (value: string) => new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

const demoDate = '2026-10-10T09:30:00Z'
export function createWorkspace(): Workspace {
  const sources: Source[] = [
    { id: 'catalog', name: 'G60_OptionList.PDF', family: 'Product catalog', locator: 'Page 18, equipment overview', excerpt: 'Illustrative catalog excerpt for the demo: equipment availability and vehicle specifications provide the baseline for the successor programme. Values in this workspace are sample values, not extracted BMW specifications.', level: 'Verified', line: 'G60', market: 'All', addedAt: demoDate },
    { id: 'feedback', name: 'G60_feedback_hackathon.xlsx', family: 'Customer feedback', locator: 'Feedback, row 214', excerpt: 'Illustrative customer comment: “The cabin is quiet and comfortable, but adjusting the climate settings takes too much attention while driving.” This is a sample excerpt, not a quote from the provided BMW data.', level: 'Interpreted', line: 'G60', market: 'EU', addedAt: demoDate },
    { id: 'study', name: 'Customer studies', family: 'Customer study', locator: 'CN_EU, cell D42', excerpt: 'Illustrative study evidence: cabin comfort matters to customers, while usability and charging convenience are potential improvement areas. The provided study workbook has no respondent counts; no sample size is inferred here.', level: 'Interpreted', line: 'All', market: 'All', addedAt: demoDate },
    { id: 'sales', name: 'sales_volumes.xlsx', family: 'Sales', locator: 'G60_G68, row 3', excerpt: 'Illustrative sales evidence: annual vehicle volumes offer business context. Vehicle sales do not establish option uptake. The 2030 values in the real workbook are forecasts and must be labeled separately.', level: 'Verified', line: 'All', market: 'All', addedAt: demoDate },
    { id: 'competitor', name: 'Segment comparison', family: 'Competitor research', locator: 'Demo comparison, Europe', excerpt: 'Illustrative competitor comparison: vehicles are compared within the same segment, market, and measurement standard. The numbers shown here are demo values. No live competitor search has been performed.', level: 'Interpreted', line: 'All', market: 'EU', addedAt: demoDate },
    { id: 'trend', name: 'Market & Trend demo', family: 'Market research', locator: 'Demo research fixture', excerpt: 'Illustrative research signal: customers may increasingly value predictable charging, simple controls, and cabin comfort. This is a future-facing assumption and requires corroboration before it informs a product commitment.', level: 'Unverified', line: 'All', market: 'All', addedAt: demoDate },
  ]
  for (const line of ['F70', 'G70'] as Line[]) sources.push({ ...sources[0], id: `catalog-${line}`, name: `${line}_OptionList.PDF`, line })
  const templates = [
    ['Predictable rapid charging', 'Powertrain', 'Reduce time and uncertainty at public charging stations.', '10-80% charging in 20 minutes', 'Demonstrate the target on a documented, repeatable charging protocol.', 95, 92, 95, 15, 91, 'pm_review', ['catalog', 'study', 'competitor']],
    ['Climate controls within easy reach', 'Usability', 'Let customers adjust cabin temperature with fewer interactions.', 'Temperature adjustment in 2 actions', 'Complete the primary climate tasks without opening a secondary menu.', 94, 86, 91, 20, 88, 'tracked', ['feedback', 'study']],
    ['Quiet, comfortable long-distance travel', 'Comfort & Space', 'Maintain cabin comfort during everyday commuting and longer journeys.', 'Customer comfort rating of 4.3/5', 'Confirm the rating in a documented study with the scale and sample disclosed.', 85, 72, 92, 25, 81, 'tracked', ['feedback', 'study', 'catalog']],
    ['More usable electric range', 'Powertrain', 'Improve electric range without compromising everyday efficiency.', 'WLTP range target of 560 km', 'Measure baseline and successor using the same WLTP protocol.', 91, 84, 88, 70, 84, 'draft', ['catalog', 'competitor']],
    ['Rear seating that feels spacious', 'Comfort & Space', 'Provide comfortable knee room for rear-seat passengers.', 'Rear legroom target of 970 mm', 'Confirm the target using the same seat-position and measurement procedure.', 74, 65, 80, 45, 76, 'pm_review', ['study', 'catalog']],
    ['Clear charging route guidance', 'Infotainment', 'Make charging stops understandable before and during a trip.', 'Charging-plan usability score of 4/5', 'Customers can identify the next charging stop and expected arrival charge.', 82, 69, 76, 30, 70, 'draft', ['feedback', 'trend']],
    ['Flexible panoramic roof offering', 'Variant & Package', 'Keep equipment choices aligned with what customers value.', 'Validate demand by market', 'Obtain purchase-level evidence before making an option uptake claim.', 55, 42, 60, 60, 48, 'challenged', ['catalog', 'sales']],
    ['Faster seat ventilation response', 'Interior', 'Improve perceived seat cooling during the first minutes of a journey.', 'PM target: 75-second response', 'Validate the target using a repeatable thermal-comfort test.', 79, 58, 77, 25, 65, 'draft', ['feedback', 'study']],
  ] as const
  const requirements: Requirement[] = templates.map((r, i) => ({ id: `D-${String(i + 1).padStart(3, '0')}`, title: r[0], domain: r[1], description: r[2], metric: r[3], acceptance: r[4], relevance: r[5], business: r[6], fit: r[7], effort: r[8], confidence: r[9], status: r[10], sourceIds: [...r[11]], line: 'G60', market: 'EU', updatedAt: demoDate, assumption: 'All evidence, scores, and targets are illustrative. Engineering feasibility and customer validation are still required.' }))
  for (const line of Object.keys(lineNames) as Line[]) {
    for (const market of Object.keys(marketNames) as Market[]) {
      if (line === 'G60' && market === 'EU') continue
      const indices = (line === 'F70' ? [1, 2, 4] : [0, 1, 2]).slice(0, market === 'CN' ? 2 : 3)
      indices.forEach((index, i) => requirements.push({ ...requirements[index], id: `D-${line}-${market}-${i + 1}`, line, market, sourceIds: ['study', 'trend'], status: 'draft', confidence: market === 'CN' ? 42 : 62, assumption: `Illustrative ${marketNames[market]} requirement. Market-specific corroboration is needed; the real dataset contains no China customer feedback.` }))
    }
  }
  const metrics: Record<string, Metric[]> = {}
  for (const line of Object.keys(lineNames) as Line[]) for (const market of Object.keys(marketNames) as Market[]) {
    metrics[scopeKey(line, market)] = [
      { id: 'range', label: 'Electric range (WLTP)', baseline: 480, competition: 510, target: 560, unit: 'km', min: 300, max: 800, lower: false, priority: 4, sourceId: 'catalog', trend: [390, 430, 480] },
      { id: 'charging', label: 'Rapid charging (10-80%)', baseline: 28, competition: 25, target: 20, unit: 'min', min: 10, max: 60, lower: true, priority: 5, sourceId: 'competitor', trend: [36, 32, 28] },
      { id: 'efficiency', label: 'Energy consumption', baseline: 16.8, competition: 16.2, target: 15.5, unit: 'kWh/100 km', min: 10, max: 30, lower: true, priority: 3, sourceId: 'catalog', trend: [19.2, 17.8, 16.8] },
      { id: 'comfort', label: 'Customer comfort rating', baseline: 3.4, competition: 3.8, target: 4.3, unit: '/ 5', min: 1, max: 5, lower: false, priority: 4, sourceId: 'study', trend: [3.1, 3.3, 3.4] },
    ]
    metrics[scopeKey(line, market)] = metrics[scopeKey(line, market)].map(m => ({ ...m, ...(m.sourceId === 'catalog' && line !== 'G60' ? { sourceId: `catalog-${line}` } : {}), ...(m.id === 'range' && market !== 'EU' ? { label: `Electric range (${market === 'US' ? 'EPA' : 'CLTC'})` } : {}) }))
    if (line === 'F70') metrics[scopeKey(line, market)] = [
      { id: 'efficiency', label: 'Fuel consumption', baseline: 6.2, competition: 5.9, target: 5.5, unit: 'L/100 km', min: 3, max: 12, lower: true, priority: 4, sourceId: 'study', trend: [6.8, 6.5, 6.2] },
      { id: 'acceleration', label: 'Acceleration (0-100 km/h)', baseline: 8.5, competition: 8.2, target: 7.8, unit: 'sec', min: 4, max: 15, lower: true, priority: 3, sourceId: 'study', trend: [9.2, 8.8, 8.5] },
      { id: 'space', label: 'Boot capacity', baseline: 380, competition: 390, target: 410, unit: 'L', min: 250, max: 600, lower: false, priority: 3, sourceId: 'study', trend: [360, 370, 380] },
      { id: 'comfort', label: 'Customer comfort rating', baseline: 3.4, competition: 3.8, target: 4.3, unit: '/ 5', min: 1, max: 5, lower: false, priority: 4, sourceId: 'study', trend: [3.1, 3.3, 3.4] },
    ]
  }
  const audits: Audit[] = [
    { id: 'initial-1', title: 'Climate controls moved to Tracked', detail: 'PM accepted the usability direction. Customer validation remains part of the acceptance criteria.', actor: 'Demo PM', time: demoDate, line: 'G60', market: 'EU' },
    { id: 'initial-2', title: 'Panoramic roof evidence challenged', detail: 'Vehicle sales cannot support a claim about option uptake. Purchase-level evidence requested.', actor: 'Demo PM', time: '2026-10-09T14:20:00Z', line: 'G60', market: 'EU' },
  ]
  return { version: 1, sources, requirements, metrics, audits, runs: [], weights: { ...defaultWeights } }
}

export function createResearch(query: string, line: Line, market: Market): ResearchRun {
  return { id: uid(), query, line, market, createdAt: new Date().toISOString(), status: 'active', notes: [], steps: [
    { name: 'Customer evidence', reason: 'Review the customer context for this question.', status: 'awaiting_review', summary: `Demo evidence review for “${query}”. The customer-study fixture highlights comfort and ease of use. ${market === 'CN' ? 'China has study evidence but no customer feedback in the provided dataset.' : 'These sample observations need confirmation against the actual feedback rows.'}`, sourceIds: ['study', ...(line === 'G60' && market === 'EU' ? ['feedback'] : [])] },
    { name: 'Market & competition', reason: 'Compare the segment and state future-facing assumptions.', status: 'planned', summary: 'The demo competitor fixture suggests a gap worth investigating. A live review must confirm comparable variants, measurement standards, and market availability. The market-trend fixture is an assumption, not a forecast.', sourceIds: [market === 'EU' ? 'competitor' : 'study', 'trend'] },
    { name: 'Requirement drafting', reason: 'Turn accepted evidence into a customer-facing requirement.', status: 'planned', summary: 'Propose a measurable successor requirement for the PM to review. The draft records the original research question, an explicit validation task, and references only the demo sources accepted in this run. It does not set a target without PM input.', sourceIds: ['study', 'trend'] },
  ] }
}

export function downloadFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function portfolioCsv(rows: Requirement[], weights: Weights, sources: Source[]) {
  const quote = (v: unknown) => {
    const text = String(v ?? '')
    return `"${(/^[=+@\-\t\r]/.test(text) ? "'" : '') + text.replaceAll('"', '""')}"`
  }
  return [['ID', 'Title', 'Vehicle line', 'Market', 'Domain', 'Status', 'Tier', 'Score', 'Confidence', 'Metric', 'Citations'], ...rows.map(r => [r.id, r.title, r.line, r.market, r.domain, statusNames[r.status], tier(composite(r, weights)), composite(r, weights).toFixed(2), `${r.confidence}%`, r.metric, r.sourceIds.map(id => { const s = sources.find(x => x.id === id); return s ? `${s.name}: ${s.locator}` : id }).join('; ')])].map(row => row.map(quote).join(',')).join('\r\n')
}
