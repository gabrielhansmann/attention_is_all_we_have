import { test, expect, type Page, type Route } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'

// Live mode talks to the backend through /api. Every call is mocked here: nothing reaches a real backend or database.
const require = createRequire(import.meta.url)
const NOW = '2026-10-12T09:00:00Z'

async function navigate(page: Page, name: string) {
  const link = page.getByRole('link', { name, exact: true })
  if (!(await link.count()) || !(await link.first().isVisible())) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name, exact: true }).click()
}
async function noViolations(page: Page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe: typeof axe }).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.html.slice(0, 200)) })))
  expect(violations).toEqual([])
}

const agents = [
  { name: 'Customer Feedback Agent', stage: 1, description: 'What customers say.', available: false },
  { name: 'Market & Trend Agent', stage: 1, description: 'Where the market is heading.', available: true },
  { name: 'Clustering Agent', stage: 2, description: 'Groups findings into themes.', available: false },
]
const conversation = { id: 'c1', title: 'US G60 infotainment dislikes', vehicle_line: 'G60', market_code: 'US', status: 'active', created_at: NOW, updated_at: NOW }
const step = (n: number, name: string, available: boolean) => ({ id: `s${n}`, position: n, agent_name: name, stage: 1, status: 'planned', plan_reason: `Because ${name}.`, planned_by: 'orchestrator', attempt: 1, available })
const planPayload = (names: [string, boolean][]) => ({ run_id: 'r1', vehicle_line: 'G60', market: 'US', steps: names.map(([n, a], i) => ({ step_id: `s${i + 1}`, position: i + 1, agent: n, stage: 1, reason: `Because ${n}.`, planned_by: 'orchestrator', available: a })) })
const run = (names: [string, boolean][]) => ({ id: 'r1', conversation_id: 'c1', vehicle_line: 'G60', market: 'US', query_text: 'q', status: 'in_progress', created_at: NOW, steps: names.map(([n, a], i) => step(i + 1, n, a)) })
const msg = (seq: number, role: string, kind: string, content: string, payload = {}, run_id: string | null = null) => ({ id: `m${seq}`, seq, conversation_id: 'c1', role, kind, run_id, step_id: null, content, payload, created_at: NOW })

const PLAN2: [string, boolean][] = [['Customer Feedback Agent', false], ['Market & Trend Agent', true]]
const PLAN1: [string, boolean][] = [['Customer Feedback Agent', false]]
const detail = (plan: [string, boolean][], changed = false) => ({
  conversation,
  messages: [
    msg(1, 'pm', 'request', 'What do US G60 owners dislike most about the infotainment?'),
    msg(2, 'orchestrator', 'plan', 'Plan text', planPayload(PLAN2), 'r1'),
    msg(3, 'orchestrator', 'system_note', 'Not built yet: Customer Feedback Agent. The plan keeps it so you can see what the question needs.', {}, 'r1'),
    ...(changed ? [msg(4, 'pm', 'plan_change', 'Plan updated', { ...planPayload(plan), removed: ['Market & Trend Agent'], added: [] }, 'r1')] : []),
  ],
  runs: [run(plan)],
})
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })

async function mockBackend(page: Page, calls: { posted?: string; edited?: string[] } = {}) {
  let changed = false
  await page.route('**/api/health', r => json(r, { status: 'ok', db: 'ok', openai_key: true, version: 'test' }))
  await page.route('**/api/agents', r => json(r, agents))
  await page.route('**/api/conversations', async r => {
    if (r.request().method() === 'POST') { calls.posted = r.request().postDataJSON().request; return json(r, detail(PLAN2), 201) }
    return json(r, changed || calls.posted ? [conversation] : [])
  })
  await page.route('**/api/conversations/c1', r => json(r, detail(changed ? PLAN1 : PLAN2, changed)))
  await page.route('**/api/runs/r1/plan', r => {
    calls.edited = r.request().postDataJSON().agents
    changed = true
    return json(r, { messages: [], run: run(PLAN1) })
  })
}

test.describe('live research (planner)', () => {
  test.beforeEach(async ({ page }) => { await page.goto('/') })

  test('a request becomes a visible plan that the PM can edit', async ({ page }) => {
    const calls: { posted?: string; edited?: string[] } = {}
    await mockBackend(page, calls)
    await navigate(page, 'Research')
    await page.getByRole('button', { name: 'Live planner (backend)', exact: true }).click()
    const live = page.getByTestId('live-research')
    await expect(live.getByText('No conversations yet.')).toBeVisible()
    await expect(live.getByText('Agents do not run yet', { exact: false })).toBeVisible()

    await live.getByLabel('Research request', { exact: true }).fill('What do US G60 owners dislike most about the infotainment?')
    await live.getByRole('button', { name: 'Plan request', exact: true }).click()
    expect(calls.posted).toBe('What do US G60 owners dislike most about the infotainment?')

    const plan = live.getByRole('article', { name: 'Plan' })
    await expect(plan.getByText('Customer Feedback Agent', { exact: true })).toBeVisible()
    await expect(plan.getByText('Market & Trend Agent', { exact: true })).toBeVisible()
    await expect(plan.getByText('Not built yet')).toHaveCount(1)          // only the agent that does not exist is flagged
    await expect(plan.getByText('G60 (5 Series)')).toBeVisible()
    await expect(live.getByText('Not built yet: Customer Feedback Agent.', { exact: false })).toBeVisible()
    await expect(live.getByRole('button', { name: /^(Accept|Retry|Reject)$/ })).toHaveCount(0)   // no fake review controls
    await noViolations(page)

    await plan.getByRole('button', { name: 'Edit plan', exact: true }).click()
    const editor = live.getByRole('form', { name: 'Edit plan' })
    await expect(editor.getByRole('button', { name: 'Save plan' })).toBeDisabled()                  // nothing changed yet
    await editor.getByLabel('Market & Trend Agent').uncheck()
    await editor.getByRole('button', { name: 'Save plan' }).click()
    await expect.poll(() => calls.edited).toEqual(['Customer Feedback Agent'])
    await expect(live.getByRole('article', { name: 'Updated plan' })).toContainText('Removed Market & Trend Agent')
    const updated = live.getByRole('article', { name: 'Updated plan' })
    await expect(updated.getByText('Market & Trend Agent', { exact: true })).toHaveCount(0)      // gone from the current plan
    await expect(updated.getByText('Customer Feedback Agent', { exact: true })).toBeVisible()
    await expect(live.getByText('Replaced by a later plan')).toHaveCount(1)                       // the earlier plan is marked, not hidden
    await expect(live.getByRole('article', { name: 'Plan', exact: true }).getByRole('button', { name: 'Edit plan' })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('a plan the backend refuses shows its reason and changes nothing', async ({ page }) => {
    await mockBackend(page)
    await page.route('**/api/runs/r1/plan', r => json(r, { detail: 'Customer Feedback Agent (or another stage 1 agent) is needed before Clustering Agent' }, 422))
    await navigate(page, 'Research')
    await page.getByRole('button', { name: 'Live planner (backend)', exact: true }).click()
    const live = page.getByTestId('live-research')
    await live.getByLabel('Research request', { exact: true }).fill('Which trends matter for the G60?')
    await live.getByRole('button', { name: 'Plan request', exact: true }).click()
    await live.getByRole('button', { name: 'Edit plan', exact: true }).click()
    const editor = live.getByRole('form', { name: 'Edit plan' })
    await editor.getByLabel('Clustering Agent').check()
    await editor.getByRole('button', { name: 'Save plan' }).click()
    await expect(editor.getByRole('alert')).toContainText('is needed before Clustering Agent')
    await expect(live.getByRole('article', { name: 'Plan' })).toBeVisible()
  })

  test('an unreachable backend is explained and the demo walkthrough still works', async ({ page }) => {
    await page.route('**/api/**', r => json(r, { detail: 'planner unavailable: OPENAI_API_KEY is not set' }, 503))
    await navigate(page, 'Research')
    await page.getByRole('button', { name: 'Live planner (backend)', exact: true }).click()
    const live = page.getByTestId('live-research')
    await expect(live.getByText('Conversations unavailable:', { exact: false })).toBeVisible()
    await live.getByLabel('Research request', { exact: true }).fill('Which trends matter?')
    await live.getByRole('button', { name: 'Plan request', exact: true }).click()
    await expect(live.getByText('planner unavailable: OPENAI_API_KEY is not set', { exact: true })).toBeVisible()   // the composer's own error
    await page.getByRole('button', { name: 'Demo walkthrough', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Ask. Review. Decide.' })).toBeVisible()
    await expect(page.getByLabel('What would you like to explore?')).toBeVisible()
  })
})

test.describe('live evidence library', () => {
  test('shows loaded sources and makes gaps visible', async ({ page }) => {
    await page.route('**/api/health', r => json(r, { status: 'ok', db: 'ok', openai_key: true, version: 'test' }))
    await page.route('**/api/evidence/filters', r => json(r, { lines: ['G60'], markets: [], domains: [], polarities: [], powertrains: [] }))
    await page.route('**/api/evidence/stats?**', r => json(r, { group_by: 'market_code', total: 0, rows: [] }))
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
    await page.goto('/')
    await navigate(page, 'Evidence library')
    await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
    const lib = page.getByTestId('live-library')
    const table = lib.getByRole('table', { name: 'Stored evidence by vehicle line and market' })
    await expect(table.getByRole('cell', { name: /No customer feedback/ })).toHaveCount(1)       // China
    await expect(table.getByRole('cell', { name: /Thin: 40 comments/ })).toHaveCount(1)          // under the 100 comment threshold
    await expect(table.getByRole('cell', { name: /4,365 comments/ })).toHaveCount(1)
    await expect(table.getByRole('cell', { name: /2025 sales 115,000/ })).toBeVisible()
    await expect(table.getByRole('cell', { name: /No 2025 sales row/ })).toHaveCount(2)
    await expect(table.getByRole('rowheader', { name: /62 catalog options/ })).toBeVisible()
    const sources = lib.getByRole('table', { name: 'Source files loaded into the evidence store' })
    await expect(sources.getByRole('row', { name: /G60_feedback_hackathon.xlsx.*5,005 comments/ })).toBeVisible()
    await expect(sources.getByRole('row', { name: /G60_OptionList.PDF.*58 text passages, 62 equipment options/ })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await noViolations(page)
  })

  test('library failures are shown without hiding the rest of the page', async ({ page }) => {
    await page.route('**/api/**', r => json(r, { detail: 'evidence store unavailable (OperationalError)' }, 503))
    await page.goto('/')
    await navigate(page, 'Evidence library')
    await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
    const lib = page.getByTestId('live-library')
    await expect(lib.getByRole('alert').filter({ hasText: 'Coverage unavailable:' })).toBeVisible()
    await expect(lib.getByRole('alert').filter({ hasText: 'Sources unavailable:' })).toBeVisible()
    await page.getByRole('button', { name: 'Demo sources', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Every claim has a source.' })).toBeVisible()
  })
})
