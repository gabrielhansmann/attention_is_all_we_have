import { expect, test } from '@playwright/test'
import { json, noOverflow, noViolations, withSession, NOW } from './helpers'

// Test fixtures only; the app's models and numerical values always come from its API.
const model = { id: 'model-1', name: 'BMW fixture family', origin: 'dataset', vehicle_line: 'TEST', identity: { basis: 'Test source model field' }, variants: [{ name: 'Reference variant', powertrain: 'ICE' }], markets: ['EU'] }
const citation = { kind: 'pdf_text', id: 'source-1', file: 'https://example.org/official-specs', locator: 'passage 1', quote: 'Test vehicle power 100 kW' }
const observation = (id: string, value: number, name?: string) => ({ id, model_id: id === 'own' ? model.id : id, name, variant: id === 'own' ? 'Reference variant' : 'Rival variant', powertrain: 'ICE', value, upper_value: null, text_value: null, unit: 'kW', standard: '', basis: 'system', period: 'current_offering', quote: citation.quote, scope_quote: 'Test vehicle variant', citation, type: 'web', retrieved_at: NOW, extracted_at: NOW })
const own = observation('own', 100)
const rivals = [observation('a', 40, 'Competitor fixture A'), observation('b', 70, 'Competitor fixture B'), observation('c', 190, 'Competitor fixture C')]
const overview = { model, variant: 'Reference variant', market: 'EU', powertrain: 'ICE', comparisons: [{ metric: 'power', label: 'System power', section: 'Performance', unit: 'kW', standard: '', basis: 'system', period: 'current_offering', direction: 'higher', own, mean: 100, median: 70, mean_range: null, median_range: null, n: 3, delta: 0, median_delta: 30, contributors: rivals, excluded: [], observations: [own, ...rivals] }], rivals: rivals.map((o) => ({ id: o.id, rival_id: o.id, name: o.name, rival_variant: o.variant, reason: 'Comparable fixture', discovery_url: citation.file, selection: 'automatic', observations: [o] })), dataset: { feedback: [], study: [], options: [], sales: [] }, research: { id: 'job-1', status: 'completed', notes: [], started_at: NOW, finished_at: NOW }, conversation_id: null, computed_at: NOW, mean_method: 'Each rival model contributes once. Reference model excluded.' }
async function setup(page: import('@playwright/test').Page) {
  await withSession(page)
  await page.route('**/api/conversations', (r) => json(r, []))
  await page.route('**/api/models', (r) => json(r, { models: [model], default_market: 'EU', markets: [{ code: 'EU', name: 'Germany / Europe' }, { code: 'CN', name: 'China' }] }))
  await page.route('**/api/models/model-1/overview?**', (r) => json(r, overview))
}
test('reference, competitors, median and mean are distinct and accessible', async ({ page }, info) => {
  await setup(page); await page.goto('/#models')
  await expect(page.getByRole('heading', { name: 'Model comparisons' })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Market', exact: true })).toContainText('Germany / Europe')
  const chart = page.getByRole('article', { name: 'System power comparison' })
  await expect(chart.getByText('Competitor median (n=3)')).toBeVisible()
  await expect(chart.getByText('Competitor mean (n=3)')).toBeVisible()
  await expect(chart.getByText('Competitor fixture B Rival variant')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Model chat', exact: true })).toBeVisible()
  await expect(page.getByText('Context ready:', { exact: false })).toContainText('3 selected competitors')
  await noOverflow(page); await noViolations(page)
  await chart.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/attention-models-${info.project.name}.png` })
  await chart.screenshot({ path: `/tmp/attention-model-chart-${info.project.name}.png` })
})
test('crawl dates, reevaluation and recrawl use the comparison API', async ({ page }) => {
  await setup(page); const validations: unknown[] = []
  await page.route('**/api/models/model-1/validate', (r) => { validations.push(r.request().postDataJSON()); return json(r, overview) })
  await page.goto('/#models')
  const chart = page.getByRole('article', { name: 'System power comparison' })
  await chart.getByText('Validate values and benchmarks', { exact: true }).click()
  await expect(chart.getByText('Crawled', { exact: false }).first()).toBeVisible()
  await chart.getByRole('button', { name: 'Recrawl source' }).first().click()
  await expect.poll(() => validations.length).toBe(1)
  expect(validations[0]).toEqual({ variant: 'Reference variant', market: 'EU', mode: 'recrawl', observation_id: 'own' })
  await page.getByRole('button', { name: 'Reevaluate evidence', exact: true }).click()
  await expect.poll(() => validations.length).toBe(2)
  expect(validations[1]).toEqual({ variant: 'Reference variant', market: 'EU', mode: 'reevaluate' })
})
test('model chat sends its server-validated scope', async ({ page }) => {
  await setup(page); let sent: Record<string, unknown> | null = null
  const detail = { conversation: { id: 'conversation-model', title: 'Model chat', vehicle_line: 'TEST', market_code: 'EU', status: 'active', created_at: NOW, updated_at: NOW }, messages: [], runs: [] }
  await page.route('**/api/conversations', (r) => { if (r.request().method() === 'POST') { sent = r.request().postDataJSON(); return json(r, detail, 201) } return json(r, []) })
  await page.route('**/api/conversations/conversation-model', (r) => json(r, detail))
  await page.goto('/#models')
  await page.getByRole('textbox', { name: 'Research request', exact: true }).fill('Compare the selected model with its competitors')
  await page.getByRole('button', { name: 'Send', exact: true }).click()
  await expect.poll(() => sent).not.toBeNull()
  expect(sent).toMatchObject({ comparison_model_id: 'model-1', comparison_variant: 'Reference variant', comparison_market: 'EU' })
})
test('collection gaps stay visible and manual competitor entry is usable', async ({ page }) => {
  await setup(page)
  await page.route('**/api/models/model-1/overview?**', (r) => json(r, { ...overview, comparisons: [], rivals: [], research: { ...overview.research, status: 'partial', notes: ['robots.txt disallows the source.'] } }))
  await page.goto('/#models')
  await expect(page.getByRole('heading', { name: 'Collect the comparison evidence' })).toBeVisible()
  await page.getByText('Research coverage and validation notes (1)', { exact: true }).click()
  await expect(page.getByText('robots.txt disallows the source.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add competitor', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByLabel('Make and model, including variant')).toBeVisible()
  await expect(page.getByRole('dialog')).toHaveAttribute('data-open')
  await noOverflow(page); await noViolations(page)
})

test('feature matrix exposes evidence gaps without invented ratings', async ({ page }) => {
  await setup(page)
  const feature = { ...own, id: 'feature-1', value: null, text_value: 'Navigation (standard)', unit: '', type: 'internal_pdf' }
  await page.route('**/api/models/model-1/overview?**', (r) => json(r, { ...overview, comparisons: [...overview.comparisons, { ...overview.comparisons[0], metric: 'connectivity', label: 'Connectivity', section: 'Connectivity', unit: '', own: feature, mean: null, median: null, n: 0, delta: null, median_delta: null, contributors: [], observations: [feature] }] }))
  await page.goto('/#models')
  const table = page.getByRole('table', { name: 'Source coverage for connectivity, assistance and comfort by model' })
  await expect(table.getByText('Navigation (standard)')).toBeVisible()
  await expect(table.getByText('No evidence collected')).toHaveCount(3)
  await table.scrollIntoViewIfNeeded()
  await noOverflow(page); await noViolations(page)
  await page.getByText('Validate connectivity claims (1)', { exact: true }).click()
  await expect(page.getByRole('button', { name: 'Reevaluate finding', exact: true })).toBeVisible()
})

test('every rival can be crawled inside the app even before a finding exists', async ({ page }) => {
  await setup(page)
  const validations: Record<string, unknown>[] = []
  const emptyRival = { ...overview.rivals[0], observations: [], sources: [] }
  await page.route('**/api/models/model-1/overview?**', (r) => json(r, { ...overview, rivals: [emptyRival] }))
  await page.route('**/api/models/model-1/validate', (r) => { validations.push(r.request().postDataJSON()); return json(r, overview) })
  await page.goto('/#models')
  await page.getByRole('button', { name: 'Crawl rival sources', exact: true }).click()
  await expect.poll(() => validations.length).toBe(1)
  expect(validations[0]).toEqual({ variant: 'Reference variant', market: 'EU', mode: 'recrawl', rival_id: 'a' })
  await page.getByRole('button', { name: 'Reevaluate rival', exact: true }).first().click()
  await expect.poll(() => validations.length).toBe(2)
  expect(validations[1]).toEqual({ variant: 'Reference variant', market: 'EU', mode: 'reevaluate', rival_id: 'a' })
})
