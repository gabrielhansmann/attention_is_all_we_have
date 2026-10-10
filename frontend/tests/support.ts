import type { Page, Route } from '@playwright/test'
import type { StoredRequirement, WorkspaceSnapshot } from '../src/types/api'

export const user = { id: 'test-user', email: 'pm@example.test', display_name: 'Database Manager', role: 'pm' }
export const config = { lines: [{ key: 'G60', label: 'Stored 5 Series' }, { key: 'F70', label: 'Stored 1 Series' }], markets: [{ key: 'EU', label: 'Stored Europe' }, { key: 'US', label: 'Stored United States' }] }
export const date = '2026-10-10T12:00:00Z'
export function emptySnapshot(): WorkspaceSnapshot {
  return { generated_at: date, counts: { feedback: 0, study_cells: 0, catalog_options: 0, pending_steps: 0 }, requirements: [], sales: [], options: [], studies: [], runs: [], results: [], audits: [] }
}
export function storedRequirement(): StoredRequirement {
  return { id: '00000000-0000-0000-0000-000000000111', code: 'R-STORED', title: 'Stored climate requirement', description: 'A requirement returned by the backend.', vehicle_line: 'G60', markets: ['EU'], status: 'pm_review', metric: 'Stored usability metric', acceptance_criteria: 'Stored validation protocol', evidence_level: 'Interpreted', assumptions: [], uncertainties: ['Needs a validation study'], created_at: date, domain: 'Stored usability domain', score: null, confidence: null, score_rationale: null, weight_vector_version: null, scored_at: null, allowed_statuses: ['tracked', 'rejected'], citations: [{ id: 'finding-1', file: 'real-feedback.xlsx', locator: 'sheet Feedback, row 81', quote: 'Original source comment.', evidence_level: 'Interpreted' }] }
}
export const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })
export async function seedSession(page: Page) {
  await page.addInitScript(() => window.sessionStorage.setItem('bmw-api-token', 'mock-session'))
}
export async function mockWorkspace(page: Page, options: { snapshot?: () => WorkspaceSnapshot; unavailable?: boolean; authenticated?: boolean } = {}) {
  if (options.authenticated !== false) await seedSession(page)
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/auth/me') return json(route, user)
    if (url.pathname === '/api/workspace/config') return json(route, config)
    if (url.pathname === '/api/workspace') return options.unavailable ? json(route, { detail: 'database unavailable' }, 503) : json(route, options.snapshot?.() ?? emptySnapshot())
    if (url.pathname === '/api/health') return json(route, { status:'ok', db:'ok', openai_key:true, version:'test' })
    return json(route, { detail: 'Unmocked test request' }, 503)
  })
}
export async function navigate(page: Page, name: string) {
  const link = page.getByRole('link', { name, exact: true })
  if (!(await link.count()) || !(await link.first().isVisible())) await page.getByRole('button', { name:'Open navigation' }).click()
  await page.getByRole('link', { name, exact:true }).click()
}
