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
