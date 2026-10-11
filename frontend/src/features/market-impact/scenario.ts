import type { Market, MarketSignal } from '@/types/api'

export const MARKETS: { key: Market; label: string; short: string }[] = [
  { key: 'US', label: 'United States', short: 'US' },
  { key: 'EU', label: 'Europe', short: 'EU' },
  { key: 'CN', label: 'China', short: 'CN' },
  { key: 'RoW', label: 'Rest of world', short: 'RoW' },
]
export type Assumption = { baseline: string; delta: string; reason: string }
export type Scenario = Record<Market, Assumption>
export type Impact = { state: 'positive' | 'negative' | 'mixed' | 'neutral' | 'unknown'; delta: number | null; baseline: number | null; resulting: number | null; error: string | null; basis: 'scenario' | 'evidence' | 'unassessed' | 'excluded' }
export const IMPACT_COLORS: Record<Impact['state'], string> = {
  positive: 'color-mix(in srgb, var(--success) 70%, var(--foreground))',
  negative: 'var(--destructive)', mixed: 'var(--warning)', neutral: 'var(--muted-foreground)', unknown: 'var(--input)',
}
export const emptyScenario = (): Scenario => Object.fromEntries(MARKETS.map(({ key }) => [key, { baseline: '', delta: '', reason: '' }])) as Scenario

function number(value: string): number | null {
  if (!value.trim()) return null
  // Accept decimal percentage points, not exponents, hexadecimal, Infinity or ambiguous commas.
  return /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim()) ? Number(value) : NaN
}

export function impact(assumption: Assumption, included: boolean): Impact {
  const baseline = number(assumption.baseline)
  const entered = number(assumption.delta)
  let error: string | null = null
  if (baseline !== null && (!Number.isFinite(baseline) || baseline < 0 || baseline > 100)) error = 'Baseline must be a number from 0 to 100%.'
  else if (included && entered !== null && (!Number.isFinite(entered) || entered < -100 || entered > 100)) error = 'Change must be a number from -100 to +100 pp.'
  else if (included && baseline !== null && entered !== null && (baseline + entered < 0 || baseline + entered > 100)) error = 'Resulting share must stay between 0 and 100%.'
  if (error) return { state: 'unknown', delta: null, baseline: null, resulting: null, error, basis: 'scenario' }
  const delta = included ? entered : 0
  const resulting = baseline !== null && delta !== null ? Math.round((baseline + delta) * 1e6) / 1e6 : null
  return { state: delta === null ? 'unknown' : delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral', delta, baseline, resulting, error: null,
    basis: !included ? 'excluded' : delta === null ? 'unassessed' : 'scenario' }
}

export function assessedImpact(assumption: Assumption, included: boolean, signal?: Pick<MarketSignal, 'direction'>): Impact {
  const result = impact(assumption, included)
  if (result.error || result.delta !== null || !signal) return result
  return { ...result, state: signal.direction === 'insufficient' ? 'unknown' : signal.direction, basis: 'evidence' }
}

const format = (value: number) => new Intl.NumberFormat('en', { maximumFractionDigits: 6 }).format(value)
export const changeLabel = (delta: number | null): string => delta === null ? 'Not assessed' : `${delta > 0 ? '+' : ''}${format(delta)} pp`
export const shareLabel = (value: number | null): string => value === null ? 'Unknown' : `${format(value)}%`


export function combineDirections(internal: MarketSignal['direction'], external?: MarketSignal['direction']): MarketSignal['direction'] {
  const signals = [internal, external]
  if (signals.includes('mixed') || (signals.includes('positive') && signals.includes('negative'))) return 'mixed'
  if (signals.includes('positive')) return 'positive'
  if (signals.includes('negative')) return 'negative'
  return 'insufficient'
}
