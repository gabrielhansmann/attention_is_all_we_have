import { test, expect, type Page, type Route } from '@playwright/test'
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

const counts = (c: Partial<Record<'feedback' | 'pdf_chunks' | 'options' | 'study_cells' | 'sales_rows', number>>) => ({ feedback: 0, pdf_chunks: 0, options: 0, study_cells: 0, sales_rows: 0, ...c })
const FEEDBACK = { id: 'a', file: 'G60_feedback_hackathon.xlsx', type: 'internal_xlsx', family: 'Customer feedback', vehicle_line: 'G60', market: null, title: null, retrieved_at: NOW, trust_tier: null, counts: counts({ feedback: 5005 }) }
const CATALOG = { id: 'b', file: 'G60_OptionList.PDF', type: 'internal_pdf', family: 'Product catalog', vehicle_line: 'G60', market: null, title: 'BMW 5er', retrieved_at: NOW, trust_tier: null, counts: counts({ pdf_chunks: 58, options: 62 }) }
const COVERAGE = {
  total_feedback: 5243, options_by_line: { G60: 62 },
  cells: [
    { line: 'G60', market: 'US', feedback: 4365, study_cells: 721, sales_2025: 78000 },
    { line: 'G60', market: 'EU', feedback: 238, study_cells: 37, sales_2025: 115000 },
    { line: 'G60', market: 'RoW', feedback: 40, study_cells: 0, sales_2025: null },
    { line: 'G60', market: 'CN', feedback: 0, study_cells: 0, sales_2025: null },
  ],
}
const LINKS = [
  { source_id: 'a', line: 'G60', market: 'US', rows: 4365 }, { source_id: 'a', line: 'G60', market: 'EU', rows: 238 },
  { source_id: 'a', line: 'G60', market: 'RoW', rows: 402 }, { source_id: 'b', line: 'G60', market: null, rows: 120 },
]
const FOUND = { url: 'https://www.autonews.example/g60-review', domain: 'autonews.example', title: 'Long-term test of the 5 Series', trust_tier: 'trade_press', findings: 2, skipped_reason: null, agent: 'Market & Trend Agent', retrieved_at: NOW, vehicle_line: 'G60', market: 'EU', request: 'What do reviewers say?', conversation_id: 'c1', conversation: 'G60 reviews', source_id: null }

/** The four reads behind the Sources view. `state` is read on every request, so a test can change it. */
async function mockLibrary(page: Page, state: { sources: unknown[]; found: unknown[] }) {
  await page.route('**/api/conversations', r => json(r, []))
  await page.route('**/api/sources', r => json(r, state.sources))
  await page.route('**/api/evidence/coverage', r => json(r, COVERAGE))
  await page.route('**/api/sources/graph', r => json(r, { links: LINKS }))
  await page.route('**/api/sources/web-research', r => json(r, state.found))
}

test.describe('sources', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('the graph links sources to the lines and markets they cover', async ({ page }) => {
    await mockLibrary(page, { sources: [FEEDBACK, CATALOG], found: [FOUND] })
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    await expect(lib.getByLabel('Summary')).toContainText('5,243')
    await expect(lib.getByLabel('Summary')).toContainText('of 4 line and market pairs have no customer feedback')
    const graph = lib.getByTestId('source-graph')
    await expect(graph.getByRole('button', { name: 'G60_OptionList.PDF, file, 120 rows' })).toBeVisible()
    await expect(graph.getByRole('button', { name: 'Long-term test of the 5 Series, website read by an agent' })).toBeVisible()
    await expect(graph.getByRole('button', { name: 'CN, market' })).toBeVisible()               // no rows: still drawn, as a gap

    const details = graph.getByLabel('Details')
    await graph.getByRole('button', { name: /G60_feedback_hackathon.xlsx, file, 5,005 rows/ }).press('Enter')
    await expect(details).toContainText('File, selected')
    await expect(details).toContainText('Customer feedback')
    await expect(details.getByRole('listitem').filter({ hasText: 'G60, US' })).toContainText('4,365')

    await graph.getByRole('button', { name: /^G60, vehicle line/ }).press('Enter')
    await expect(details.getByRole('listitem').filter({ hasText: 'CN' })).toContainText('No rows')
    await details.getByRole('button', { name: 'Open coverage table' }).click()
    await expect(lib.getByRole('tab', { name: 'Coverage' })).toHaveAttribute('aria-selected', 'true')
    await noOverflow(page)
    await noViolations(page)
  })

  test('files and coverage are listed in their tabs and gaps stay visible', async ({ page }) => {
    await mockLibrary(page, { sources: [FEEDBACK, CATALOG], found: [] })
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    await lib.getByRole('tab', { name: 'Coverage' }).click()
    const table = lib.getByRole('table', { name: 'Stored evidence by vehicle line and market' })
    await expect(table.getByRole('cell', { name: /No customer feedback/ })).toHaveCount(1)       // CN
    await expect(table.getByRole('cell', { name: /Thin: 40 comments/ })).toHaveCount(1)          // under the 100 comment threshold
    await expect(table.getByRole('cell', { name: /4,365 comments/ })).toHaveCount(1)
    await expect(table.getByRole('cell', { name: /2025 sales 115,000/ })).toBeVisible()
    await expect(table.getByRole('cell', { name: /No 2025 sales row/ })).toHaveCount(2)
    await expect(table.getByRole('rowheader', { name: /62 catalog options/ })).toBeVisible()
    await noViolations(page)

    await lib.getByRole('tab', { name: 'Files' }).click()
    const sources = lib.getByRole('table', { name: 'Source files loaded into the evidence store' })
    await expect(sources.getByRole('row', { name: /G60_feedback_hackathon.xlsx.*5,005 comments/ })).toBeVisible()
    await expect(sources.getByRole('row', { name: /G60_OptionList.PDF.*58 text passages, 62 equipment options/ })).toBeVisible()
    await noOverflow(page)
    await noViolations(page)
  })

  test('a file is uploaded, what was stored is reported, and the tables refresh', async ({ page }) => {
    const row = (file: string, sales_rows: number) => ({ id: file, file, type: 'internal_xlsx', family: 'Sales volumes', vehicle_line: null, market: null, title: file, retrieved_at: NOW, trust_tier: null, counts: counts({ sales_rows }) })
    const state = { sources: [row('sales_volumes.xlsx', 36)], found: [] }
    const posted: { url?: URL; body?: string | null; type?: string } = {}
    await mockLibrary(page, state)
    await page.route('**/api/sources?**', async r => {
      const req = r.request()
      Object.assign(posted, { url: new URL(req.url()), body: req.postData(), type: req.headers()['content-type'] })
      if (posted.url!.searchParams.get('filename') === 'broken.xlsx') return json(r, { detail: 'The spreadsheet layout was not recognised.' }, 422)
      state.sources.push(row('G60_dealer_sales.xlsx', 12))
      return json(r, { file: 'G60_dealer_sales.xlsx', kind: 'sales', replaced: false, notes: ['1 cells skipped: no market code or no number.'], counts: counts({ sales_rows: 12 }) }, 201)
    })
    await page.goto('/#sources')
    await page.getByRole('tab', { name: 'Files' }).click()
    await expect(page.getByRole('form', { name: 'Add a file' })).toHaveCount(0)                 // closed until asked for
    await page.getByRole('button', { name: 'Add a file' }).click()
    const form = page.getByRole('form', { name: 'Add a file' })
    const upload = form.getByRole('button', { name: 'Upload file' })
    await expect(upload).toBeDisabled()                                                         // nothing chosen yet

    await form.getByLabel('File').setInputFiles({ name: 'broken.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK-broken') })
    await upload.click()
    await expect(form.getByRole('alert')).toHaveText('Upload failed: The spreadsheet layout was not recognised.')

    await form.getByLabel('File').setInputFiles({ name: 'G60_dealer_sales.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK-sales') })
    await expect(form.getByRole('alert')).toHaveCount(0)
    await expect(form.getByLabel('Vehicle line')).toContainText('G60')                          // offered from the file name
    await upload.click()
    await expect(form.getByRole('status')).toContainText('Stored G60_dealer_sales.xlsx: 12 sales rows.')
    await expect(form.getByRole('status')).toContainText('1 cells skipped')
    expect(posted.url!.searchParams.get('line')).toBe('G60')
    expect(posted.url!.searchParams.get('replace')).toBeNull()
    expect(posted.body).toBe('PK-sales')
    expect(posted.type).toBe('application/octet-stream')
    await expect(page.getByRole('table', { name: 'Source files loaded into the evidence store' }).getByRole('row', { name: /G60_dealer_sales.xlsx.*12 sales rows/ })).toBeVisible()

    // a name that is already loaded has to be sent as a replacement, and the form says so first
    await form.getByLabel('File').setInputFiles({ name: 'sales_volumes.xlsx', mimeType: 'application/octet-stream', buffer: Buffer.from('PK-again') })
    await expect(form.getByText('sales_volumes.xlsx is already loaded.', { exact: false })).toBeVisible()
    await form.getByRole('button', { name: 'Replace file' }).click()
    await expect.poll(() => posted.url!.searchParams.get('replace')).toBe('true')
    await noOverflow(page)
    await noViolations(page)
  })

  test('a website is added, a page an agent read is stored, and a stored page is removed', async ({ page }) => {
    const site = (id: string, url: string, title: string) => ({ id, file: url, type: 'web', family: 'Website', vehicle_line: 'G60', market: 'EU', title, retrieved_at: NOW, trust_tier: 'trade_press', counts: counts({ pdf_chunks: 14 }) })
    const state: { sources: unknown[]; found: unknown[] } = { sources: [FEEDBACK], found: [FOUND] }
    const posts: Record<string, unknown>[] = []
    let removed: string | undefined
    await mockLibrary(page, state)
    await page.route('**/api/sources/web', r => {
      const body = r.request().postDataJSON()
      posts.push(body)
      if (body.url.includes('intranet')) return json(r, { detail: 'Only pages on the public internet can be added.' }, 422)
      if (body.url === 'https://press.example/g60' && !body.replace && state.sources.length > 1) return json(r, { detail: 'This page is already stored.' }, 409)
      if (body.url === FOUND.url) state.found = [{ ...FOUND, source_id: 'w2' }]
      if (!body.replace) state.sources.push(site(body.url === FOUND.url ? 'w2' : 'w1', body.url, body.url === FOUND.url ? FOUND.title : 'The new 5 Series'))
      return json(r, { file: body.url, kind: 'web', replaced: !!body.replace, notes: [], counts: counts({ pdf_chunks: 14 }) }, 201)
    })
    await page.route('**/api/sources/w1', r => { removed = r.request().method(); state.sources = state.sources.filter((s) => (s as { id: string }).id !== 'w1'); return r.fulfill({ status: 204 }) })
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    await lib.getByRole('tab', { name: 'Websites' }).click()
    const form = lib.getByRole('form', { name: 'Add a website' })
    const add = form.getByRole('button', { name: 'Add website' })
    await expect(add).toBeDisabled()
    await expect(lib.getByText('No websites are stored yet.', { exact: false })).toBeVisible()
    await noViolations(page)

    await form.getByLabel('Web address').fill('https://intranet.example/wiki')
    await add.click()
    await expect(form.getByRole('alert')).toHaveText('Not stored: Only pages on the public internet can be added.')

    await form.getByLabel('Web address').fill('https://press.example/g60')
    await add.click()
    await expect(form.getByRole('status')).toContainText('Stored press.example: 14 text passages.')
    expect(posts.at(-1)).toEqual({ url: 'https://press.example/g60', replace: false })
    const stored = lib.getByRole('table', { name: 'Websites stored in the evidence store' })
    await expect(stored.getByRole('row', { name: /The new 5 Series.*Trade press.*G60, EU.*14 passages/ })).toBeVisible()

    // the same address again is refused first, then fetched anew on request
    await form.getByLabel('Web address').fill('https://press.example/g60')
    await add.click()
    await expect(form.getByRole('alert')).toContainText('already stored')
    await form.getByRole('button', { name: 'Fetch again' }).click()
    await expect(form.getByRole('status')).toContainText('Fetched again press.example')
    expect(posts.at(-1)).toMatchObject({ url: 'https://press.example/g60', replace: true })

    // a page an agent read is stored with the scope and tier of the run it came from
    const found = lib.getByRole('table', { name: 'Websites read by agents during research runs' })
    await expect(found.getByRole('row', { name: /Long-term test of the 5 Series.*Market & Trend Agent.*2 findings/ })).toBeVisible()
    await found.getByRole('button', { name: 'Store autonews.example' }).click()
    await expect(found.getByRole('row', { name: /Long-term test/ })).toContainText('Stored')
    expect(posts.at(-1)).toEqual({ url: FOUND.url, line: 'G60', market: 'EU', trust_tier: 'trade_press' })
    await expect(stored.getByRole('row')).toHaveCount(3)                                         // header and two pages

    await stored.getByRole('button', { name: 'Remove press.example' }).click()                   // asks before removing
    expect(removed).toBeUndefined()
    await stored.getByRole('button', { name: 'Remove page' }).click()
    await expect(stored.getByRole('row')).toHaveCount(2)
    expect(removed).toBe('DELETE')
    await noOverflow(page)
    await noViolations(page)
  })

  test('failures are shown without hiding the rest of the page', async ({ page }) => {
    const down = (r: Route) => json(r, { detail: 'evidence store unavailable (OperationalError)' }, 503)
    await page.route('**/api/conversations', r => json(r, []))
    for (const path of ['sources', 'evidence/coverage', 'sources/graph', 'sources/web-research']) await page.route(`**/api/${path}`, down)
    await page.goto('/#sources')
    const lib = page.getByTestId('live-library')
    await expect(lib.getByRole('alert').filter({ hasText: 'Sources unavailable:' })).toBeVisible()
    await lib.getByRole('tab', { name: 'Coverage' }).click()
    await expect(lib.getByRole('alert').filter({ hasText: 'Coverage unavailable:' })).toBeVisible()
    await expect(lib.getByRole('tab', { name: 'Websites' })).toBeVisible()
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
