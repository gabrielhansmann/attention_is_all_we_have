import type { StoredRequirement } from './types/api'

export type Page = 'overview' | 'requirements' | 'research' | 'evidence' | 'reports'
export const statusLabel = (value: string) => value.replaceAll('_', ' ').replace(/^pm\b/, 'PM').replace(/^./, c => c.toUpperCase())
export const formatNumber = (value: number) => new Intl.NumberFormat('en', { maximumFractionDigits: 2 }).format(value)
export const dateLabel = (value: string) => new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
export const confidenceLabel = (value: number | null) => value === null ? 'Not scored' : `${formatNumber(value * 100)}%`
export function downloadFile(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a'); link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function portfolioCsv(rows: StoredRequirement[]) {
  const quote = (value: unknown) => {
    const text = String(value ?? '')
    return `"${(/^[=+@\-\t\r]/.test(text) ? "'" : '') + text.replaceAll('"', '""')}"`
  }
  return [['ID', 'Code', 'Title', 'Vehicle line', 'Markets', 'Domain', 'Status', 'Score', 'Confidence', 'Metric', 'Acceptance criteria', 'Citations'],
    ...rows.map(r => [r.id, r.code, r.title, r.vehicle_line, r.markets.join('; '), r.domain, r.status, r.score, r.confidence, r.metric, r.acceptance_criteria,
      r.citations.map(c => `${c.file}: ${c.locator}`).join('; ')])].map(row => row.map(quote).join(',')).join('\r\n')
}
