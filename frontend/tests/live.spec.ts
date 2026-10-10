import { test, expect, type Page } from '@playwright/test'
import { NOW, json, noOverflow, noViolations, withSession } from './helpers'

// Every backend call is mocked: nothing reaches a real backend or database.
const conversation = { id: 'c1', title: 'US G60 infotainment dislikes', vehicle_line: 'G60', market_code: 'US', status: 'active', created_at: NOW, updated_at: NOW }
const msg = (seq: number, role: string, kind: string, content: string, payload = {}, step_id: string | null = null) =>
  ({ id: `m${seq}`, seq, conversation_id: 'c1', role, kind, run_id: 'r1', step_id, content, payload, created_at: NOW })
const step = (n: number, agent: string, status: string) => ({ id: `s${n}`, position: n, agent_name: agent, stage: 1, status, plan_reason: `Because ${agent}.`, planned_by: 'orchestrator', attempt: 1, available: true })
const run = (status: string, steps: ReturnType<typeof step>[]) => ({ id: 'r1', conversation_id: 'c1', vehicle_line: 'G60', market: 'US', query_text: 'q', status, created_at: NOW, steps })

const request = msg(1, 'pm', 'request', 'What do US G60 owners dislike most about the infotainment?')
const call1 = msg(2, 'orchestrator', 'system_note', 'Calling Customer Feedback Agent: asks what owners say.', { decision: { agent: 'Customer Feedback Agent' } }, 's1')
const card1 = msg(3, 'agent', 'step_card', 'Owners find the voice assistant unreliable (G60_feedback.xlsx, row 12).', { agent: 'Customer Feedback Agent', failed: false, output: { findings: [{}, {}] } }, 's1')
const call2 = msg(4, 'orchestrator', 'system_note', 'Calling Competitor Agent: the findings point at a rival feature.', { decision: { agent: 'Competitor Agent' } }, 's2')
const final = msg(5, 'orchestrator', 'final_result', 'Research result: voice assistant complaints.')

// What the backend returns while the orchestrator works through the request, one stage per read.
const stages = [
  { messages: [request], runs: [run('in_progress', [])] },
  { messages: [request, call1], runs: [run('in_progress', [step(1, 'Customer Feedback Agent', 'running')])] },
  { messages: [request, call1, card1, call2], runs: [run('in_progress', [step(1, 'Customer Feedback Agent', 'accepted'), step(2, 'Competitor Agent', 'running')])] },
  { messages: [request, call1, card1, call2, final], runs: [run('completed', [step(1, 'Customer Feedback Agent', 'accepted'), step(2, 'Competitor Agent', 'accepted')])] },
]

async function mockBackend(page: Page, calls: { posted?: string } = {}) {
  let reads = 0
  await page.route('**/api/conversations', async r => {
    if (r.request().method() === 'POST') { calls.posted = r.request().postDataJSON().request; return json(r, { conversation, ...stages[0] }, 201) }
    return json(r, calls.posted ? [conversation] : [])
  })
  await page.route('**/api/conversations/c1', r => json(r, { conversation, ...stages[Math.min(reads++, stages.length - 1)] }))
}

test.describe('research', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('the orchestrator calls agents on its own and the thread shows each decision and result', async ({ page }) => {
    const calls: { posted?: string } = {}
    await mockBackend(page, calls)
    await page.goto('/')
    const live = page.getByTestId('live-research')
    await expect(live.getByText('No conversations yet.')).toBeVisible()

    await live.getByLabel('Research request', { exact: true }).fill('What do US G60 owners dislike most about the infotainment?')
    await live.getByRole('button', { name: 'Send', exact: true }).click()
    expect(calls.posted).toBe('What do US G60 owners dislike most about the infotainment?')

    // the first agent is called, then its cited result arrives and a second agent is chosen because of it
    await expect(live.getByText('Calling Customer Feedback Agent: asks what owners say.')).toBeVisible()
    await expect(live.getByRole('status')).toContainText('is working')
    await expect(live.getByRole('button', { name: 'Working' })).toBeDisabled()          // one request at a time
    const card = live.getByRole('article', { name: 'Customer Feedback Agent result' })
    await expect(card).toContainText('voice assistant unreliable')
    await expect(card.getByText('2 findings')).toBeVisible()
    await expect(live.getByText('Calling Competitor Agent: the findings point at a rival feature.')).toBeVisible()
    await expect(live.getByText('Research result: voice assistant complaints.')).toBeVisible()
    await expect(live.getByRole('status')).toHaveCount(0)
    await expect(live.getByLabel('Follow-up request')).toBeVisible()

    // nothing for the person to approve, edit or start
    await expect(live.getByRole('button', { name: /^(Accept|Edit|Retry|Reject|Start research)/ })).toHaveCount(0)
    await noOverflow(page)
    await noViolations(page)
  })

  test('a backend failure is explained in place', async ({ page }) => {
    await page.route('**/api/**', r => r.request().url().endsWith('/api/health') || r.request().url().endsWith('/api/auth/me') ? r.fallback() : json(r, { detail: 'orchestrator unavailable: OPENAI_API_KEY is not set' }, 503))
    await page.goto('/')
    const live = page.getByTestId('live-research')
    await expect(live.getByText('Conversations unavailable:', { exact: false })).toBeVisible()
    await live.getByLabel('Research request', { exact: true }).fill('Which trends matter?')
    await live.getByRole('button', { name: 'Send', exact: true }).click()
    await expect(live.getByText('orchestrator unavailable: OPENAI_API_KEY is not set', { exact: true })).toBeVisible()
  })
})

test.describe('sources', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('shows loaded sources and makes gaps visible', async ({ page }) => {
    await page.route('**/api/sources', r => json(r, [
      { id: 'a', file: 'G60_feedback_hackathon.xlsx', type: 'internal_xlsx', family: 'Customer feedback', vehicle_line: 'G60', market: null, title: null, retrieved_at: NOW, counts: { feedback: 5005, pdf_chunks: 0, options: 0, study_cells: 0, sales_rows: 0 } },
      { id: 'b', file: 'G60_OptionList.PDF', type: 'internal_pdf', family: 'Product catalog', vehicle_line: 'G60', market: null, title: 'BMW 5er', retrieved_at: NOW, counts: { feedback: 0, pdf_chunks: 58, options: 62, study_cells: 0, sales_rows: 0 } },
    ]))
    await page.route('**/api/evidence/coverage', r => json(r, {
      total_feedback: 5243, options_by_line: { G60: 62 },
      cells: [
        { line: 'G60', market: 'US', feedback: 4365, study_cells: 721, sales_2025: 78000 },
        { line: 'G60', market: 'EU', feedback: 238, study_cells: 37, sales_2025: 115000 },
        { line: 'G60', market: 'RoW', feedback: 40, study_cells: 0, sales_2025: null },
        { line: 'G60', market: 'CN', feedback: 0, study_cells: 0, sales_2025: null },
      ],
    }))
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    const table = lib.getByRole('table', { name: 'Stored evidence by vehicle line and market' })
    await expect(table.getByRole('cell', { name: /No customer feedback/ })).toHaveCount(1)       // CN
    await expect(table.getByRole('cell', { name: /Thin: 40 comments/ })).toHaveCount(1)          // under the 100 comment threshold
    await expect(table.getByRole('cell', { name: /4,365 comments/ })).toHaveCount(1)
    await expect(table.getByRole('cell', { name: /2025 sales 115,000/ })).toBeVisible()
    await expect(table.getByRole('cell', { name: /No 2025 sales row/ })).toHaveCount(2)
    await expect(table.getByRole('rowheader', { name: /62 catalog options/ })).toBeVisible()
    const sources = lib.getByRole('table', { name: 'Source files loaded into the evidence store' })
    await expect(sources.getByRole('row', { name: /G60_feedback_hackathon.xlsx.*5,005 comments/ })).toBeVisible()
    await expect(sources.getByRole('row', { name: /G60_OptionList.PDF.*58 text passages, 62 equipment options/ })).toBeVisible()
    await noOverflow(page)
    await noViolations(page)
  })

  test('failures are shown without hiding the rest of the page', async ({ page }) => {
    await page.route('**/api/sources', r => json(r, { detail: 'evidence store unavailable (OperationalError)' }, 503))
    await page.route('**/api/evidence/coverage', r => json(r, { detail: 'evidence store unavailable (OperationalError)' }, 503))
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    await expect(lib.getByRole('alert').filter({ hasText: 'Coverage unavailable:' })).toBeVisible()
    await expect(lib.getByRole('alert').filter({ hasText: 'Sources unavailable:' })).toBeVisible()
  })
})

test.describe('evidence', () => {
  test('searches with filters and shows cited hits', async ({ page }) => {
    await withSession(page)
    await page.route('**/api/evidence/filters', r => json(r, { lines: ['G60'], markets: [{ key: 'US', label: 'USA' }], domains: [], polarities: ['negative'], powertrains: [] }))
    await page.route('**/api/evidence/stats?**', r => json(r, { group_by: 'market_code', total: 2, rows: [{ key: 'US', n: 2 }] }))
    await page.route('**/api/evidence/search?**', r => json(r, { query: 'seat', source: 'feedback', hits: [
      { citation: { kind: 'feedback', id: 'f1', file: 'G60_feedback_hackathon.xlsx', locator: 'row 12', quote: 'The seat ventilation is too weak.' }, text: 'The seat ventilation is too weak.', meta: { vehicle_line: 'G60', market_code: 'US' }, score: 0.9 },
    ] }))
    await page.goto('/#evidence')
    await expect(page.getByRole('table', { name: 'Comment counts by group' })).toContainText('2')
    await page.getByLabel('Search', { exact: true }).fill('seat ventilation')
    await page.getByRole('button', { name: 'Search', exact: true }).click()
    await expect(page.getByRole('blockquote').or(page.locator('blockquote'))).toContainText('The seat ventilation is too weak.')
    await expect(page.getByText('G60_feedback_hackathon.xlsx')).toBeVisible()
    await noOverflow(page)
    await noViolations(page)
  })
})
