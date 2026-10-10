import { ApiError } from '@/lib/api'
import type { SourceInfo, TrustTier } from '@/types/api'

export const fmt = (n: number) => n.toLocaleString('en-US')

/** What was extracted from a source file, in words. */
export function contents(c: SourceInfo['counts']): string {
  const parts = [
    c.feedback && `${fmt(c.feedback)} comments`,
    c.pdf_chunks && `${fmt(c.pdf_chunks)} text passages`,
    c.options && `${fmt(c.options)} equipment options`,
    c.study_cells && `${fmt(c.study_cells)} study cells`,
    c.sales_rows && `${fmt(c.sales_rows)} sales rows`,
  ].filter(Boolean)
  return parts.join(', ') || 'Nothing extracted'
}

export type Load<T> = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; data: T }

export const errorText = (e: unknown) => (e instanceof ApiError ? e.message : 'Something went wrong.')

const TIERS: Record<TrustTier, string> = { oem: 'Manufacturer', trade_press: 'Trade press', forum_social: 'Forum or social' }
export const TIER_OPTIONS = (Object.keys(TIERS) as TrustTier[]).map((value) => ({ value, label: TIERS[value] }))
export const tierLabel = (t: TrustTier | null) => (t ? TIERS[t] : 'Not rated')

export const isWeb = (s: SourceInfo) => s.type === 'web'

export function domainOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

export const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Unknown date'

export const clip = (text: string, max: number) => (text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text)
