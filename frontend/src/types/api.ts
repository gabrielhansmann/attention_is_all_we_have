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
  counts: { feedback: number; pdf_chunks: number; options: number; study_cells: number; sales_rows: number }
}

export interface UploadResult {
  file: string
  kind: 'pdf' | 'feedback' | 'sales' | 'studies'
  replaced: boolean
  counts: SourceInfo['counts']
  notes: string[]
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
  document: { source_id: string; type: string; openable: boolean } | null
}
