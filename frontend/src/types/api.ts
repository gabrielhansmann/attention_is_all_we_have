// Mirrors backend/app/api/schemas.py. Every piece of evidence arrives with its citation.

export type Line = 'F70' | 'G60' | 'G68' | 'G70'
export type Market = 'EU' | 'CN' | 'US' | 'RoW'
export type Polarity = 'positive' | 'negative' | 'request'
export type Powertrain = 'ICE' | 'PHEV' | 'BEV'
export type SearchSource = 'feedback' | 'docs'
export type GroupBy =
  | 'vehicle_line'
  | 'market_code'
  | 'country'
  | 'powertrain'
  | 'polarity'
  | 'feedback_type'
  | 'domain'

export interface Citation {
  kind: string
  id: string
  file: string
  locator: string
  quote: string
}

export interface Hit {
  citation: Citation
  text: string
  meta: Record<string, string | number | null>
  score: number | null
}

export interface SearchResponse {
  query: string
  source: SearchSource
  hits: Hit[]
}

export interface MarketOptionsResponse {
  line: Line
  options: Hit[]
  truncated: boolean
}

export interface MarketAssessmentRequest {
  line: Line
  option_id?: string
  feature?: string
}

export interface MarketSignal {
  market: Market
  direction: 'positive' | 'negative' | 'mixed' | 'insufficient'
  explanation: string
  total_feedback: number
  matched_total: number
  counts: { positive: number; request: number; negative: number }
  reviewed: number
  signal_counts: { benefit: number; risk: number; unclear: number }
  evidence: { citation: Citation; stance: 'supports' | 'risk' | 'mixed' | 'unclear'; reason: string }[]
}

export interface MarketAssessmentResponse {
  line: Line
  feature: string
  catalog_citation: Citation | null
  basis: string
  query_terms: string[]
  markets: MarketSignal[]
}

export interface MarketWebEvidence {
  market: Market | null; stance: 'supports' | 'risk' | 'context'; url: string; title: string; summary: string;
  retrieved_at: string; source_type: string; scope: string; reason: string;
}
export interface MarketWebAssessmentResponse {
  public_query: string | null
  context?: MarketWebEvidence[]
  notes?: string[]
  markets: { market: Market; direction: MarketSignal['direction']; evidence: MarketWebEvidence[]; status?: 'complete' | 'partial' | 'unmapped'; explanation?: string }[]
}

export interface StatsResponse {
  group_by: string
  total: number
  rows: { key: string | null; n: number }[]
}

export interface Health {
  status: 'ok' | 'degraded'
  db: 'ok' | 'unavailable' | 'not_configured'
  openai_key: boolean
  version: string
}

export interface FilterOptions {
  lines: Line[]
  markets: { key: Market; label: string }[]
  domains: { key: string; label: string }[]
  polarities: Polarity[]
  powertrains: Powertrain[]
}

export interface EvidenceFilters {
  line?: Line
  market?: Market
  domain?: string
  polarity?: Polarity
  powertrain?: Powertrain
}

// ---------------------------------------------------------------- chat (mirrors backend/app/api/schemas.py)

export interface Conversation {
  id: string
  title: string
  vehicle_line: string | null
  market_code: string | null
  status: 'active' | 'archived'
  created_at: string
  updated_at: string
}

export type MessageKind =
  | 'request'
  | 'plan'
  | 'plan_change'
  | 'step_card'
  | 'pushback'
  | 'final_result'
  | 'system_note'

export interface ChatMessage {
  id: string
  seq: number
  conversation_id: string
  role: 'pm' | 'orchestrator' | 'agent' | 'system'
  kind: MessageKind
  run_id: string | null
  step_id: string | null
  content: string
  payload: Record<string, unknown>
  created_at: string
}

export interface ResearchReview {
  scope_note: string
  requirements: {
    requirement_id: string
    title: string
    support: { finding_id: string; text: string; source: string; locator: string; market: string; evidence_level: string }[]
    counter: { finding_id: string; text: string; source: string; locator: string; market: string; evidence_level: string }[]
    markets: { market: string; status: string; finding_ids: string[] }[]
    actions: { priority: 'high' | 'medium'; action: string; reason: string }[]
  }[]
}

export interface RunStep {
  id: string
  position: number
  agent_name: string
  stage: number
  status: 'planned' | 'running' | 'awaiting_review' | 'accepted' | 'rejected'
  plan_reason: string | null
  planned_by: 'orchestrator' | 'pm'
  attempt: number
  available: boolean
}

export interface Run {
  id: string
  conversation_id: string | null
  vehicle_line: string
  market: string
  query_text: string | null
  status: 'in_progress' | 'completed' | 'aborted'
  created_at: string
  steps: RunStep[]
}

export interface ConversationDetail {
  conversation: Conversation
  messages: ChatMessage[]
  runs: Run[]
}

export interface PostResult {
  messages: ChatMessage[]
  run: Run | null
}

// ---------------------------------------------------------------- evidence library

export interface SourceInfo {
  id: string
  file: string
  type: string
  family: string
  vehicle_line: string | null
  market: string | null
  title: string | null
  retrieved_at: string
  trust_tier: TrustTier | null
  counts: { feedback: number; pdf_chunks: number; options: number; study_cells: number; sales_rows: number }
}

export type TrustTier = 'oem' | 'trade_press' | 'forum_social'

export interface UploadResult {
  file: string
  kind: 'pdf' | 'feedback' | 'sales' | 'studies' | 'web'
  replaced: boolean
  counts: SourceInfo['counts']
  notes: string[]
}

export interface WebSourceRequest {
  url: string
  line?: string
  market?: string
  trust_tier?: TrustTier
  replace?: boolean
}

/** Rows one source holds for one vehicle line and market; null means not tied to a line or market. */
export interface SourceLink {
  source_id: string
  line: string | null
  market: string | null
  rows: number
}

export interface SourceGraph {
  links: SourceLink[]
}

/** A website a web agent read during a run. `source_id` is set once the page is stored as a source. */
export interface WebFind {
  url: string
  domain: string
  title: string | null
  trust_tier: TrustTier | null
  findings: number
  skipped_reason: string | null
  agent: string
  retrieved_at: string | null
  vehicle_line: string | null
  market: string | null
  request: string | null
  conversation_id: string | null
  conversation: string | null
  source_id: string | null
}

export interface CoverageCell {
  line: string
  market: string
  feedback: number
  study_cells: number
  sales_2025: number | null
}

export interface Coverage {
  cells: CoverageCell[]
  options_by_line: Record<string, number>
  total_feedback: number
}

// ---------------------------------------------------------------- authentication

export interface AuthUser {
  id: string
  email: string
  display_name: string
  role: 'pm' | 'admin'
}

export interface LoginResult {
  token: string
  expires_at: string
  user: AuthUser
}

// ---------------------------------------------------------------- source viewer

export interface EvidencePassage {
  id: string
  label: string | null
  text: string
  cited: boolean
}

export interface EvidenceContext {
  kind: string
  id: string
  file: string
  locator: string
  title: string | null
  page: number | null
  passages: EvidencePassage[]
  vehicle_line: string | null
  market_code: string | null
  document: { source_id: string; type: string; openable: boolean; url?: string | null } | null
}

// ---------------------------------------------------------------- requirements, tracking, dossiers

export type RequirementStatus = 'draft' | 'pm_review' | 'tracked' | 'rejected' | 'challenged' | 'superseded'
export type DecisionAction = 'approve' | 'reject' | 'challenge' | 'supersede' | 'reopen' | 'acknowledge'

/** A statement an agent wrote: its text, the findings it rests on, and their citations. */
export interface Statement {
  text: string
  finding_ids: string[]
  citations: { finding_id?: string; source?: string; locator?: string }[]
}

export interface RequirementPayload {
  title: string
  description: Statement
  metric: Statement | null
  acceptance_criteria: Statement[]
  domain_label: string | null
  markets: string[]
  evidence_level: string
  assumptions: string[]
  uncertainties: string[]
  linked_finding_ids: string[]
}

export interface ScoreComponentOut {
  name: string
  value: number
  weight: number
  contribution: number
}

export interface RequirementScore {
  composite: number
  proposed_tier: string
  confidence: number
  customer_relevance: number
  business_signal: number
  strategic_fit: number
  effort_proxy: number
  weights: Record<string, number>
  rationale: string
  thin: string[]
  missing: string[]
  breakdown: ScoreComponentOut[]
}

export interface TrackingFlag {
  flag_type: 'new_evidence' | 'contradicting' | 'stale'
  reason: string
  detected_at: string
  citations: { finding_id?: string; source?: string; locator?: string }[]
}

export interface Requirement {
  id: string
  code: string
  run_id: string | null
  conversation_id: string | null
  vehicle_line: string
  market: string
  title: string
  status: RequirementStatus
  payload: RequirementPayload
  score: RequirementScore | null
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  tracked_at: string | null
  created_at: string
  updated_at: string
  actions: DecisionAction[]
  flags: TrackingFlag[]
  evidence: Record<string, unknown>[]
}

export interface RequirementHistoryEvent {
  id: string
  actor: string
  action: string
  rationale: string | null
  timestamp: string
}

export interface RequirementDetail extends Requirement {
  history: RequirementHistoryEvent[]
}

export interface RequirementList {
  requirements: Requirement[]
  counts: Partial<Record<RequirementStatus, number>>
}

export interface TrackingState {
  requirements: Requirement[]
  last_checked: string | null
}

export interface TrackingResult {
  checked: number
  summary: string
  flags: { flag_type: string; requirement_code: string | null; reason: string }[]
  skipped: { item: string; reason: string }[]
  errors: string[]
}

export interface Dossier {
  run_id: string
  conversation_id: string | null
  title: string
  vehicle_line: string
  market: string
  created_at: string | null
  dossier: string
  findings: Record<string, unknown>[]
}
