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

export interface AgentInfo {
  name: string
  stage: number
  description: string
  available: boolean
}

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
  human_readable_summary?: string | null
  pm_note?: string | null
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
  counts: { feedback: number; pdf_chunks: number; options: number; study_cells: number; sales_rows: number; findings: number }
}

export interface CoverageCell {
  line: string
  market: string
  feedback: number
  study_cells: number
  sales_volume: number | null
}

export interface Coverage {
  sales_year: number | null
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

// ---------------------------------------------------------------- database workspace
export interface ScopeOption { key: string; label: string }
export interface WorkspaceConfig { lines: ScopeOption[]; markets: ScopeOption[] }
export interface StoredCitation { id: string; file: string; locator: string; quote: string; evidence_level: string }
export interface StoredRequirement {
  id: string; code: string | null; title: string; description: string; vehicle_line: string; markets: string[]
  status: string; metric: string | null; acceptance_criteria: string | null; evidence_level: string | null
  assumptions: string[]; uncertainties: string[]; created_at: string; domain: string | null
  score: number | null; confidence: number | null; score_rationale: string | null
  weight_vector_version: string | null; scored_at: string | null; allowed_statuses: string[]; citations: StoredCitation[]
}
export interface SalesRow {
  id: string; vehicle_line: string; market_code: string; year: number; volume: number; is_forecast: boolean; file: string; locator: string
}
export interface CatalogRow {
  id: string; vehicle_line: string; code: string; name: string; description: string | null; file: string; locator: string
  standard_variants: number; optional_variants: number
}
export interface StudyRow {
  id: string; vehicle_line: string; market_code: string; model: string; question: string; metric: string
  answer_option: string | null; value: number; file: string; locator: string
}
export interface WorkspaceRun {
  id: string; conversation_id: string | null; query_text: string | null; vehicle_line: string; market: string
  status: string; created_at: string; awaiting_review: number
}
export interface AcceptedResult {
  id: string; agent_name: string; summary: string | null; output: Record<string, unknown>; resolved_at: string | null
  resolved_by: string | null; run_id: string; conversation_id: string | null; run_status: string; vehicle_line: string; market: string
}
export interface DecisionEvent {
  id: string; entity_type: string; entity_id: string; action: string; actor: string; rationale: string | null; timestamp: string
  before: Record<string, unknown> | null; after: Record<string, unknown> | null
}
export interface WorkspaceSnapshot {
  generated_at: string; counts: { feedback: number; study_cells: number; catalog_options: number; pending_steps: number }
  requirements: StoredRequirement[]; sales: SalesRow[]; options: CatalogRow[]; studies: StudyRow[]
  runs: WorkspaceRun[]; results: AcceptedResult[]; audits: DecisionEvent[]
}
