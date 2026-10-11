import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { authed, closeMenu, json, noOverflow, noViolations, openMenu, withSession } from './helpers'

const option = (id: string, text: string, code: string) => ({ citation: { kind: 'option', id, file: 'catalog.pdf', locator: `page 3, SA ${code}`, quote: text }, text, meta: { code }, score: null })
const options = [option('option-1', 'Seat ventilation', '453'), option('option-2', 'Panoramic roof', '402')]
const markets = ['US', 'EU', 'CN', 'RoW'] as const
const emptyAssessment = (line = 'G60') => ({ line, feature: 'Seat ventilation', catalog_citation: options[0]!.citation,
  basis: 'Local feedback signal, not a market-share forecast.', query_terms: ['seat ventilation'],
  markets: markets.map((market) => ({ market, direction: 'insufficient', explanation: `No matched feedback in ${market}.`, total_feedback: 10,
    matched_total: 0, counts: { positive: 0, request: 0, negative: 0 }, reviewed: 0, evidence: [] })) })
const assessed = () => ({ ...emptyAssessment(), markets: markets.map((market) => ({ market,
  direction: market === 'US' ? 'positive' : market === 'EU' ? 'negative' : market === 'RoW' ? 'mixed' : 'insufficient',
  explanation: market === 'CN' ? 'No customer feedback is loaded for G60 in this market.' : 'Matching customer feedback supports this direction.',
  total_feedback: market === 'CN' ? 0 : 100, matched_total: market === 'CN' ? 0 : market === 'RoW' ? 2 : 1,
  counts: { positive: market === 'US' || market === 'RoW' ? 1 : 0, request: 0, negative: market === 'EU' || market === 'RoW' ? 1 : 0 }, reviewed: market === 'CN' ? 0 : market === 'RoW' ? 2 : 1,
  evidence: market === 'CN' ? [] : [{ citation: { kind: 'feedback', id: `feedback-${market}`, file: 'feedback.xlsx', locator: 'row 1', quote: 'Customer comment about seat ventilation' },
    stance: market === 'EU' ? 'risk' : 'supports', reason: 'Recorded feature feedback' }, ...(market === 'RoW' ? [{
      citation: { kind: 'feedback', id: 'feedback-RoW-negative', file: 'feedback.xlsx', locator: 'row 2', quote: 'Customer complaint about seat ventilation' },
      stance: 'risk', reason: 'Recorded feature feedback',
    }] : [])],
})) })

test.beforeEach(async ({ page }) => {
  await withSession(page)
  await page.route('**/api/conversations', (r) => json(r, []))
  await page.route('**/api/market-impact/web-assessment', (r) => json(r, { public_query: 'seat ventilation', markets: markets.map((market) => ({ market, direction: 'insufficient', evidence: [] })) }))
  await page.route('**/api/market-impact/assessment', (r) => {
    expect(authed(r)).toBe(true)
    return json(r, emptyAssessment(r.request().postDataJSON().line))
  })
  await page.route('**/api/market-impact/options?*', (r) => {
    expect(authed(r)).toBe(true)
    return json(r, { line: new URL(r.request().url()).searchParams.get('line'), options, truncated: false })
  })
})

test('maps gains and losses, preserves feature assumptions, and exports a labeled scenario', async ({ page }, info) => {
  await page.goto('/#market-impact')
  await expect(page.getByRole('heading', { name: 'Choose a feature to begin' })).toBeVisible()
  await expect(page.getByLabel('Baseline share (%)')).toBeDisabled()
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await page.getByLabel('Baseline share (%)').fill('12.5')
  await page.getByLabel('Assumed change (pp)').fill('1.25')
  await page.getByLabel('Reason or source').fill('Customer study scenario assumption')
  await expect(page.getByText('13.75%', { exact: true })).toBeVisible()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await page.getByRole('button', { name: 'China', exact: false }).click()
  await page.getByLabel('Assumed change (pp)').fill('-0.5')
  await expect(page.locator('path[data-market=CN]').first()).toHaveAttribute('data-impact', 'negative')
  await expect(page.locator('path[data-market=EU]').first()).toHaveAttribute('data-impact', 'unknown')
  await page.getByTestId('world-map').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/market-impact-${info.project.name}-populated.png`, fullPage: true, scale: 'css' })
  await page.getByTestId('world-map').screenshot({ path: `/tmp/market-impact-${info.project.name}-geometry.png`, scale: 'css' })
  await noViolations(page)
  await noOverflow(page)

  await page.getByRole('switch', { name: 'Include feature' }).click()
  await expect(page.getByLabel('Assumed change (pp)')).toHaveValue('-0.5')
  await expect(page.getByLabel('Assumed change (pp)')).toBeDisabled()
  await expect(page.locator('path[data-market=CN]').first()).toHaveAttribute('data-impact', 'neutral')
  await page.getByRole('switch', { name: 'Include feature' }).click()
  await expect(page.locator('path[data-market=CN]').first()).toHaveAttribute('data-impact', 'negative')

  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '402 · Panoramic roof' }).click()
  await expect(page.getByLabel('Assumed change (pp)')).toHaveValue('')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByLabel('Assumed change (pp)')).toHaveValue('-0.5')

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export scenario' }).click()
  const download = await downloadPromise
  const report = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(report.basis).toContain('not a validated forecast')
  expect(report.catalog_citation.id).toBe('option-1')
  expect(report.markets.find((m: { market: string }) => m.market === 'CN').result.delta).toBe(-0.5)

  await page.getByLabel('Baseline share (%)').fill('0.1')
  await expect(page.getByRole('alert')).toHaveText('Resulting share must stay between 0 and 100%.')
  await expect(page.getByRole('button', { name: 'Export scenario' })).toBeDisabled()
  await expect(page.locator('path[data-market=CN]').first()).toHaveAttribute('data-impact', 'unknown')
  await page.getByRole('button', { name: 'Reset scenario' }).click()
  await expect(page.getByLabel('Assumed change (pp)')).toHaveValue('')
})

test('empty and unavailable catalogs allow an explicit custom feature; mobile navigation works', async ({ page }, info) => {
  await page.route('**/api/market-impact/options?*', (r) => json(r, { line: 'G60', options: [], truncated: false }))
  await page.goto('/#market-impact')
  await expect(page.getByText('No optional equipment is loaded for G60.', { exact: false })).toBeVisible()
  await page.screenshot({ path: `/tmp/market-impact-${info.project.name}-empty.png`, fullPage: true, scale: 'css' })
  await noViolations(page)
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: 'Custom optional feature' }).click()
  await page.getByLabel('Feature name').fill('Adaptive comfort package')
  await page.getByLabel('Assumed change (pp)').fill('0')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'neutral')
  await page.route('**/api/market-impact/options?*', (r) => json(r, { detail: 'Optional equipment catalog is unavailable.' }, 503))
  await page.getByLabel('Vehicle line').click()
  await page.getByRole('option', { name: 'F70', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('catalog is unavailable')
  await expect(page.getByLabel('Assumed change (pp)')).toBeDisabled()
  await page.getByLabel('Vehicle line').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/market-impact-${info.project.name}-error.png`, fullPage: true, scale: 'css' })
  await noViolations(page)
  await noOverflow(page)
  await page.route('**/api/market-impact/options?*', (r) => json(r, { line: 'F70', options, truncated: false }))
  await page.getByRole('button', { name: 'Retry catalog' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await openMenu(page)
  await expect(page.getByRole('link', { name: 'Market impact', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.screenshot({ path: `/tmp/market-impact-${info.project.name}-menu.png`, fullPage: true, scale: 'css', animations: 'disabled' })
  await closeMenu(page)
})

test('shows loading and opens the real catalog citation', async ({ page }, info) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/market-impact/options?*', async (r) => { await hold; await json(r, { line: 'G60', options, truncated: false }) })
  await page.route('**/api/evidence/option/option-1/context', (r) => json(r, {
    kind: 'option', id: 'option-1', file: 'catalog.pdf', locator: 'page 3, SA 453', title: 'Equipment', page: 3,
    passages: [{ id: 'p1', text: 'Seat ventilation', label: 'SA 453', cited: true }], vehicle_line: 'G60', market_code: null, document: null,
  }))
  await page.goto('/#market-impact')
  await expect(page.getByRole('status')).toContainText('Loading optional equipment')
  await page.screenshot({ path: `/tmp/market-impact-${info.project.name}-loading.png`, fullPage: true, scale: 'css' })
  release()
  await expect(page.getByRole('status')).toHaveCount(0)
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await page.getByRole('button', { name: 'View catalog source' }).click()
  await expect(page.getByRole('dialog', { name: 'Source', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByText('Seat ventilation', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close source' }).click()
})

test('selecting a feature automatically assesses markets and shows cited feedback without share inputs', async ({ page }, info) => {
  await page.route('**/api/market-impact/assessment', (r) => {
    expect(authed(r)).toBe(true)
    expect(r.request().postDataJSON()).toEqual({ line: 'G60', option_id: 'option-1' })
    return json(r, assessed())
  })
  await page.route('**/api/evidence/feedback/feedback-US/context', (r) => json(r, {
    kind: 'feedback', id: 'feedback-US', file: 'feedback.xlsx', locator: 'row 1', title: 'Feedback', page: null,
    passages: [{ id: 'p1', text: 'Customer comment about seat ventilation', label: 'row 1', cited: true }],
    vehicle_line: 'G60', market_code: 'US', document: null,
  }))
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByText('Assessment complete.', { exact: false })).toBeVisible()
  await expect(page.getByLabel('Assumed change (pp)')).toHaveValue('')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await expect(page.locator('path[data-market=EU]').first()).toHaveAttribute('data-impact', 'negative')
  await expect(page.locator('path[data-market=RoW]').first()).toHaveAttribute('data-impact', 'mixed')
  await page.getByText('View 1 sample comment', { exact: true }).click()
  await expect(page.getByText('Customer comment about seat ventilation', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'View feedback source 1' }).click()
  await expect(page.getByRole('dialog', { name: 'Source', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Close source' }).click()
  await page.getByLabel('Assumed change (pp)').fill('-0.5')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'negative')
  await page.getByRole('button', { name: 'Reset scenario' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await page.getByRole('switch', { name: 'Include feature' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'neutral')
  await page.getByRole('switch', { name: 'Include feature' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await page.getByRole('button', { name: 'China', exact: false }).click()
  await expect(page.getByText('No customer feedback is loaded for G60 in this market.', { exact: true })).toBeVisible()
  await page.getByTestId('world-map').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/market-assessment-${info.project.name}-populated.png`, scale: 'css' })
  await noViolations(page)
  await noOverflow(page)
})

test('assessment loading and outage are visible and can be retried for a custom feature', async ({ page }, info) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/market-impact/assessment', async (r) => { await hold; await json(r, { detail: 'Market assessment is unavailable. Try again.' }, 503) })
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Assessing customer feedback' })).toBeVisible()
  await page.screenshot({ path: `/tmp/market-assessment-${info.project.name}-loading.png`, scale: 'css' })
  release()
  await expect(page.getByRole('alert')).toContainText('Market assessment is unavailable')
  await page.screenshot({ path: `/tmp/market-assessment-${info.project.name}-error.png`, scale: 'css' })
  await noViolations(page)
  await page.route('**/api/market-impact/assessment', (r) => json(r, assessed()))
  await page.getByRole('button', { name: 'Retry assessment' }).click()
  await expect(page.getByText('Assessment complete.', { exact: false })).toBeVisible()
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: 'Custom optional feature' }).click()
  await page.getByLabel('Feature name').fill('Seat ventilation')
  await page.route('**/api/market-impact/assessment', (r) => {
    expect(r.request().postDataJSON()).toEqual({ line: 'G60', feature: 'Seat ventilation' })
    return json(r, assessed())
  })
  await page.getByRole('button', { name: 'Assess feature', exact: true }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await page.getByLabel('Feature name').fill('Other feature')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'unknown')
})

test('a late response from a previous feature cannot overwrite the selected feature', async ({ page }) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/market-impact/assessment', async (r) => {
    if (r.request().postDataJSON().option_id === 'option-1') {
      await hold
      await json(r, assessed()).catch(() => {})
    } else {
      const result = assessed()
      result.markets[0]!.direction = 'negative'
      await json(r, result)
    }
  })
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Assessing customer feedback' })).toBeVisible()
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '402 · Panoramic roof' }).click()
  await expect(page.getByRole('heading', { name: 'Panoramic roof', exact: true })).toBeVisible()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'negative')
  release()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'negative')
})


const publicResult = (direction = 'negative') => ({ public_query: 'seat ventilation', context: [{ market: null, stance: 'context', url: 'https://www.bmw.com/feature-context', title: 'Global feature context', summary: 'Seat ventilation is available on some models.', retrieved_at: '2026-10-11T12:00:00Z', source_type: 'verified public page', scope: 'general context, no market direction', reason: 'Feature availability.' }], markets: markets.map((market) => ({
  market, direction: market === 'US' ? direction : 'insufficient', evidence: market === 'US' ? [{
    market, stance: direction === 'negative' ? 'risk' : 'supports', url: 'https://www.jdpower.com/public-study', title: 'Public US study',
    summary: 'US owners report that seat ventilation can be difficult to use.', retrieved_at: '2026-10-11T12:00:00Z',
    source_type: 'public research/review', scope: 'market-specific', reason: 'A public US study identifies a usability risk.',
  }] : [],
})) })

test('public research loads independently and conflicting evidence stays visible as trade-offs', async ({ page }, info) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/market-impact/assessment', (r) => json(r, assessed()))
  await page.route('**/api/market-impact/web-assessment', async (r) => { expect(authed(r)).toBe(true); await hold; await json(r, publicResult()) })
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  await expect(page.getByRole('status').filter({ hasText: 'Researching public web' })).toBeVisible()
  release()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'mixed')
  await expect(page.getByRole('link', { name: 'Public US study' })).toHaveAttribute('href', 'https://www.jdpower.com/public-study')
  await expect(page.getByText('A public US study identifies a usability risk.', { exact: true })).toBeVisible()
  await page.getByText('General web context (1)', { exact: true }).click()
  await expect(page.getByRole('link', { name: 'Global feature context', exact: true })).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export scenario' }).click()
  const report = JSON.parse(await readFile((await (await downloadPromise).path())!, 'utf8'))
  expect(report.public_research.public_query).toBe('seat ventilation')
  expect(report.markets.find((m: { market: string }) => m.market === 'US').result.state).toBe('mixed')
  await page.getByTestId('world-map').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/market-web-${info.project.name}-populated.png`, fullPage: true, scale: 'css' })
  await noViolations(page)
  await noOverflow(page)
})

test('web outage preserves internal results and a previous web reply cannot change the current feature', async ({ page }) => {
  await page.route('**/api/market-impact/assessment', (r) => json(r, assessed()))
  await page.route('**/api/market-impact/web-assessment', (r) => json(r, { detail: 'Public web research is unavailable.' }, 503))
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByRole('alert')).toHaveText('Public web research is unavailable.')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'positive')
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  await page.route('**/api/market-impact/web-assessment', async (r) => {
    if (r.request().postDataJSON().option_id === 'option-1') { await hold; await json(r, publicResult('positive')).catch(() => {}) }
    else await json(r, publicResult())
  })
  await page.getByRole('button', { name: 'Retry research' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Researching public web' })).toBeVisible()
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '402 · Panoramic roof' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'mixed')
  release()
  await expect(page.getByRole('link', { name: 'Public US study' })).toBeVisible()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'mixed')
})

test('public results appear before internal feedback and survive its outage; retry only reloads internal evidence', async ({ page }, info) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => { release = resolve })
  let internalCalls = 0
  let webCalls = 0
  await page.route('**/api/market-impact/assessment', async (r) => {
    internalCalls++
    if (internalCalls === 1) { await hold; await json(r, { detail: 'Internal feedback is unavailable.' }, 503) }
    else await json(r, assessed())
  })
  await page.route('**/api/market-impact/web-assessment', async (r) => { webCalls++; await json(r, publicResult()) })
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'negative')
  await expect(page.getByRole('link', { name: 'Public US study' })).toBeVisible()
  release()
  await expect(page.getByRole('alert')).toContainText('Internal feedback is unavailable.')
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'negative')
  await expect(page.getByRole('button', { name: /United States/ })).toContainText('Internal unavailable')
  await page.screenshot({ path: `/tmp/market-integration-${info.project.name}-partial.png`, fullPage: true, scale: 'css' })
  await page.getByRole('button', { name: 'Retry assessment' }).click()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'mixed')
  expect(internalCalls).toBe(2)
  expect(webCalls).toBe(1)
  await noViolations(page)
  await noOverflow(page)
})

test('partial public research shows its gap and retries without discarding internal results', async ({ page }, info) => {
  let internalCalls = 0
  let webCalls = 0
  await page.route('**/api/market-impact/assessment', async (r) => { internalCalls++; await json(r, assessed()) })
  await page.route('**/api/market-impact/web-assessment', async (r) => {
    webCalls++
    const result = publicResult()
    await json(r, { ...result, notes: webCalls === 1 ? ['China research is incomplete.'] : [],
      markets: result.markets.map((m) => ({ ...m, status: webCalls === 1 && m.market === 'CN' ? 'partial' : 'complete' })) })
  })
  await page.goto('/#market-impact')
  await page.getByLabel('Optional feature', { exact: true }).click()
  await page.getByRole('option', { name: '453 · Seat ventilation' }).click()
  await expect(page.getByText('China research is incomplete.', { exact: true })).toBeVisible()
  await expect(page.locator('path[data-market=US]').first()).toHaveAttribute('data-impact', 'mixed')
  await page.getByRole('button', { name: 'Retry research' }).click()
  await expect(page.getByText('China research is incomplete.', { exact: true })).toHaveCount(0)
  expect(internalCalls).toBe(1)
  expect(webCalls).toBe(2)
  await page.screenshot({ path: `/tmp/market-integration-${info.project.name}-complete.png`, fullPage: true, scale: 'css' })
  await page.getByRole('region', { name: 'United States evidence', exact: true }).screenshot({ path: `/tmp/market-integration-${info.project.name}-evidence.png`, scale: 'css' })
  await noViolations(page)
  await noOverflow(page)
})
