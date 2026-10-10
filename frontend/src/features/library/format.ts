import type { SourceInfo } from '@/types/api'

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
