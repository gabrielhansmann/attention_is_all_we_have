import { test, expect, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import type axe from 'axe-core'

const require = createRequire(import.meta.url)
async function navigate(page: Page, name: string) {
  const link = page.getByRole('link', { name, exact: true })
  if (!(await link.count()) || !(await link.first().isVisible())) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name, exact: true }).click()
}
test.beforeEach(async ({ page }) => { await page.goto('/') })

test('overview, scope controls, and navigation work without page overflow', async ({ page }, testInfo) => {
  await expect(page.getByRole('heading', { name: 'Build what comes next.' })).toBeVisible()
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(page.getByRole('dialog').getByText('Demo workspace', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Close dialog' }).click()
  } else {
    await expect(page.locator('.sidebar').getByText('Demo workspace', { exact: true })).toBeVisible()
  }
  await page.getByLabel('Vehicle line', { exact: true }).selectOption('F70')
  await expect(page.getByRole('button', { name: 'Fuel consumption', exact: true })).toBeVisible()
  await page.getByLabel('Market', { exact: true }).selectOption('CN')
  await navigate(page, 'Requirements')
  await expect(page.getByRole('heading', { name: 'Evidence into action.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Predictable rapid charging', exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByLabel('Vehicle line', { exact: true }).selectOption('G60')
  await page.getByLabel('Market', { exact: true }).selectOption('EU')
  await navigate(page, 'Overview')
  await page.screenshot({ path: `/tmp/attention-overview-${testInfo.project.name}.png`, fullPage: true })
})

test('a successor target requires a reason, persists, and appears in the decision history', async ({ page }) => {
  await page.getByRole('button', { name: 'Edit Electric range (WLTP) target' }).click()
  await page.getByLabel('Successor target (km)', { exact: true }).fill('590')
  await page.getByRole('button', { name: 'Save target', exact: true }).click()
  await expect(page.getByLabel('Reason for the target')).toBeFocused()
  await page.getByLabel('Reason for the target').fill('Target aligns with the customer range concern.')
  await page.getByRole('button', { name: 'Save target', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Edit Electric range (WLTP) target' })).toContainText('590')
  await expect(page.getByText('Electric range (WLTP) target updated', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Edit Electric range (WLTP) target' })).toContainText('590')
})

test('requirements filter, review, and persist a PM approval with its reason', async ({ page }) => {
  await navigate(page, 'Requirements')
  await page.getByLabel('Search requirements', { exact: true }).fill('rapid charging')
  await expect(page.locator('.requirement-table tbody tr')).toHaveCount(1)
  await page.getByRole('button', { name: 'Predictable rapid charging', exact: true }).click()
  await page.getByRole('button', { name: 'Approve & track', exact: true }).click()
  await expect(page.getByLabel('Reason for your decision')).toBeFocused()
  await page.getByLabel('Reason for your decision').fill('Approve the direction, pending protocol validation.')
  await page.getByRole('button', { name: 'Approve & track', exact: true }).click()
  await expect(page.locator('.requirement-table tbody tr')).toContainText('Tracked')
  await page.reload()
  await page.getByLabel('Search requirements', { exact: true }).fill('rapid charging')
  await expect(page.locator('.requirement-table tbody tr')).toContainText('Tracked')
  await page.getByLabel('Status', { exact: true }).selectOption('draft')
  await expect(page.getByRole('heading', { name: 'No requirements match these filters' })).toBeVisible()
})

test('research only advances on acceptance and produces a draft after the final review', async ({ page }) => {
  await navigate(page, 'Research')
  await page.getByLabel('What would you like to explore?').fill('Make climate adjustment easier for customers')
  await page.getByRole('button', { name: 'Start research', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Accept & continue', exact: true })).toHaveCount(1)
  await expect(page.getByText('Research reviewed. Direction recorded.', { exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Accept & continue', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Add a review reason')
  for (let i = 0; i < 3; i++) {
    await page.getByLabel('Your review reason or steering note').fill(`Accepted demo contribution ${i + 1} with its limitations.`)
    await page.getByRole('button', { name: 'Accept & continue', exact: true }).click()
    if (i < 2) await expect(page.getByText('Research reviewed. Direction recorded.', { exact: true })).toHaveCount(0)
  }
  await expect(page.getByRole('heading', { name: 'Research reviewed. Direction recorded.' })).toBeVisible()
  await page.getByRole('button', { name: 'Review draft', exact: true }).click()
  await expect(page.getByLabel('Title', { exact: true })).toHaveValue('Make climate adjustment easier for customers')
  await expect(page.getByLabel('Metric or successor target')).toHaveValue('Successor target to be set by the PM')
})

test('a rejected step remains gated and can continue with a visible coverage gap', async ({ page }) => {
  await navigate(page, 'Research')
  await page.getByLabel('What would you like to explore?').fill('Explore rear-seat comfort')
  await page.getByRole('button', { name: 'Start research', exact: true }).click()
  await page.getByLabel('Your review reason or steering note').fill('The customer fixture does not support this scope.')
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Continuing records a coverage gap')
  await page.getByRole('button', { name: 'Continue with gap', exact: true }).click()
  for (let i = 0; i < 2; i++) {
    await page.getByLabel('Your review reason or steering note').fill('Accept this limited demo contribution.')
    await page.getByRole('button', { name: 'Accept & continue', exact: true }).click()
  }
  await page.getByRole('button', { name: 'Review draft', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('Coverage gap')
})

test('documents are registered locally without claiming ingestion or verification', async ({ page }) => {
  await navigate(page, 'Evidence library')
  await page.getByRole('button', { name: 'Add document', exact: true }).click()
  await page.getByLabel('Document (up to 10 MB)').setInputFiles({ name: 'dealer-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('Customer wants easier climate controls.') })
  await page.getByRole('button', { name: 'Add document', exact: true }).last().click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await page.getByRole('button', { name: /dealer-notes.txt/ }).click()
  await expect(page.getByRole('dialog')).toContainText('Not parsed')
  await expect(page.getByRole('dialog')).toContainText('Customer wants easier climate controls.')
  await page.getByRole('button', { name: 'Close dialog' }).click()
  await page.reload()
  await expect(page.getByRole('button', { name: /dealer-notes.txt/ })).toBeVisible()
})

test('filtered CSV exports include only matching requirements and citations', async ({ page }) => {
  await navigate(page, 'Requirements')
  await page.getByLabel('Search requirements', { exact: true }).fill('rapid charging')
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export portfolio', exact: true }).click()
  const file = await downloading
  expect(file.suggestedFilename()).toBe('requirements-G60-EU.csv')
  const csv = await readFile((await file.path())!, 'utf8')
  expect(csv).toContain('Predictable rapid charging')
  expect(csv).toContain('G60_OptionList.PDF: Page 18')
  expect(csv).not.toContain('Faster seat ventilation response')
})

test('citation dialogs work with the keyboard and return focus to the trigger', async ({ page }) => {
  const trigger = page.getByRole('button', { name: 'Electric range (WLTP)', exact: true })
  await trigger.focus(); await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog')).toContainText('Illustrative source excerpt')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(trigger).toBeFocused()
})

test('the report includes targets, source locators, and decision context', async ({ page }, testInfo) => {
  await navigate(page, 'Reports')
  await expect(page.getByRole('heading', { name: '5 Series successor programme' })).toBeVisible()
  await expect(page.locator('.programme-report')).toContainText('Feedback, row 214')
  await expect(page.locator('.programme-report')).toContainText('Decision history')
  if (testInfo.project.name === 'desktop') {
    const pdf = await page.pdf({ path: '/tmp/attention-programme-report.pdf', format: 'A4' })
    expect(pdf.subarray(0, 4).toString()).toBe('%PDF')
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('main views pass automated WCAG checks', async ({ page }) => {
  for (const name of ['Overview', 'Requirements', 'Research', 'Evidence library', 'Reports']) {
    await navigate(page, name)
    await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
    const violations = await page.evaluate(async () => {
      const engine = (window as unknown as { axe: typeof axe }).axe
      return (await engine.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations
    })
    expect(violations, `${name} accessibility violations`).toEqual([])
  }
})

test('the retained backend evidence browser renders API citations and exact counts', async ({ page }) => {
  await page.route('**/api/evidence/filters', route => route.fulfill({ json: { lines: ['G60'], markets: [{ key: 'EU', label: 'Europe' }], domains: [], polarities: ['negative'], powertrains: ['BEV'] } }))
  await page.route('**/api/evidence/stats?**', route => route.fulfill({ json: { group_by: 'market_code', total: 3, rows: [{ key: 'EU', n: 3 }] } }))
  let requestedQuery = ''
  await page.route('**/api/evidence/search?**', route => {
    requestedQuery = new URL(route.request().url()).searchParams.get('q') || ''
    return route.fulfill({ json: { query: requestedQuery, source: 'feedback', hits: [{ citation: { kind: 'feedback', id: 'fixture-1', file: 'api-test-fixture.xlsx', locator: 'Feedback, row 7', quote: 'The seat ventilation takes too long to respond.' }, text: 'Improve seat ventilation response.', meta: { vehicle_line: 'G60', market_code: 'EU' }, score: 0.8 }] } })
  })
  await navigate(page, 'Evidence library')
  await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
  const live = page.locator('.live-evidence')
  await expect(live.getByRole('heading', { name: 'Evidence', exact: true })).toBeVisible()
  await expect(live.getByRole('row', { name: 'Total 3', exact: true })).toBeVisible()
  await live.getByLabel('Search', { exact: true }).fill('seat ventilation')
  await live.getByRole('button', { name: 'Search', exact: true }).click()
  await expect(live.getByText('api-test-fixture.xlsx', { exact: true })).toBeVisible()
  await expect(live).toContainText('Feedback, row 7')
  await expect(live.getByRole('blockquote')).toHaveText('The seat ventilation takes too long to respond.')
  expect(requestedQuery).toBe('seat ventilation')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe: typeof axe }).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations)
  expect(violations).toEqual([])
  await page.getByRole('button', { name: 'Demo sources', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Every claim has a source.' })).toBeVisible()
})

test('backend evidence failures are shown and the local demo remains available', async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ status: 503, json: { detail: 'Evidence service unavailable.' } }))
  await navigate(page, 'Evidence library')
  await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
  await expect(page.locator('.live-evidence').getByText('Filters unavailable: Evidence service unavailable.', { exact: true })).toBeVisible()
  await page.locator('.live-evidence').getByLabel('Search', { exact: true }).fill('comfort')
  await page.locator('.live-evidence').getByRole('button', { name: 'Search', exact: true }).click()
  await expect(page.locator('.live-evidence section[aria-labelledby="results-h"]')).toContainText('Evidence service unavailable.')
  await page.getByRole('button', { name: 'Demo sources', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Every claim has a source.' })).toBeVisible()
})
