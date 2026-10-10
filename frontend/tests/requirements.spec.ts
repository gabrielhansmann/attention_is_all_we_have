import { test, expect, type Page } from '@playwright/test'
import { NOW, json, noOverflow, noViolations, withSession } from './helpers'

// Every backend call is mocked: nothing reaches a real backend or database.
const stmt = (text: string, ids = ['f1']) => ({ text, finding_ids: ids, citations: ids.map((id) => ({ finding_id: id, source: 'G60_feedback.xlsx', locator: 'sheet A, row 12' })) })
const score = (c: number, b: number, composite: number, tier: string) => ({ composite, proposed_tier: tier, confidence: 0.7, customer_relevance: c, business_signal: b, strategic_fit: 0.5, effort_proxy: 0.5, weights: {}, rationale: 'Two independent sources agree.', thin: [], missing: [], breakdown: [] })
const req = (n: number, title: string, status: string, sc: ReturnType<typeof score> | null, extra = {}) => ({
  id: `q${n}`, code: `R-000${n}`, run_id: 'r1', conversation_id: 'c1', vehicle_line: 'G60', market: 'US', title, status,
  payload: { title, description: stmt(`${title} for US owners.`), metric: stmt('Comfort within 120 seconds'), acceptance_criteria: [stmt('Verified on a hot-soak test')], domain_label: 'Comfort & Space', markets: ['US'], evidence_level: 'Verified', assumptions: ['Cabin starts at 40 C'], uncertainties: [], linked_finding_ids: ['f1'] },
  score: sc, decided_by: null, decided_at: null, decision_note: null, tracked_at: null, created_at: NOW, updated_at: NOW,
  actions: status === 'draft' ? ['approve', 'reject', 'challenge'] : status === 'tracked' ? ['challenge', 'supersede', 'acknowledge'] : ['reopen'], flags: [],
  evidence: [{ id: 'f1', text: 'Seat ventilation too weak', source: 'G60_feedback.xlsx', locator: 'sheet A, row 12', citations: [{ kind: 'feedback', id: 'e1', file: 'G60_feedback.xlsx', locator: 'sheet A, row 12', quote: 'Ventilation is weak' }] }], ...extra,
})

async function mock(page: Page, reqs: ReturnType<typeof req>[], decisions: { body?: unknown } = {}) {
  await page.route('**/api/conversations', (r) => json(r, []))
  await page.route('**/api/requirements', (r) => json(r, { requirements: reqs, counts: {} }))
  await page.route('**/api/requirements/*/decision', (r) => {
    decisions.body = r.request().postDataJSON()
    const id = r.request().url().split('/').at(-2)
    const hit = reqs.find((x) => x.id === id)!
    hit.status = 'tracked'; hit.actions = ['challenge', 'supersede', 'acknowledge']
    return json(r, { ...hit, history: [] })
  })
}

test.describe('requirements', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('review, approve with one click, and ask for a reason when rejecting', async ({ page }) => {
    const sent: { body?: unknown } = {}
    await mock(page, [req(1, 'Stronger seat ventilation', 'draft', score(0.8, 0.4, 0.62, 'Tier 2 (should-have)')), req(2, 'Wireless charging pad', 'draft', score(0.5, 0.7, 0.5, 'Tier 2 (should-have)'))], sent)
    await page.goto('/#requirements')
    const page_ = page.getByTestId('requirements')
    await expect(page_.getByRole('heading', { name: 'Requirements' })).toBeVisible()
    const card = page_.getByRole('article', { name: /Stronger seat ventilation/ })
    await expect(card).toContainText('Comfort within 120 seconds')
    await expect(card).toContainText('Verified on a hot-soak test')
    await expect(card.getByRole('button', { name: /Source 1/ }).first()).toBeVisible()
    await page.screenshot({ path: test.info().outputPath('review.png'), fullPage: true })
    await noOverflow(page)
    await noViolations(page)

    // a reason is required to reject
    await card.getByRole('button', { name: 'Reject' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByRole('button', { name: 'Reject', exact: true })).toBeDisabled()
    await dialog.getByLabel('Reason').fill('Out of scope for this generation')
    await expect(dialog.getByRole('button', { name: 'Reject', exact: true })).toBeEnabled()
    await dialog.getByRole('button', { name: 'Cancel' }).click()

    await card.getByRole('button', { name: 'Approve and track' }).click()
    await expect.poll(() => sent.body).toEqual({ action: 'approve' })
  })

  test('priorities re-rank when the weights change', async ({ page }) => {
    await mock(page, [req(1, 'Stronger seat ventilation', 'draft', score(0.9, 0.2, 0.6, 'Tier 2 (should-have)')), req(2, 'Wireless charging pad', 'draft', score(0.3, 0.9, 0.5, 'Tier 2 (should-have)'))])
    await page.goto('/#requirements?tab=priorities')
    const ranked = page.getByTestId('ranked')
    await expect(ranked.first()).toContainText('Stronger seat ventilation')
    const business = page.getByRole('slider', { name: 'Business' })
    await business.focus()
    for (let i = 0; i < 14; i++) await page.keyboard.press('ArrowRight')     // business weight up to 95%
    await expect(ranked.first()).toContainText('Wireless charging pad')
    await page.screenshot({ path: test.info().outputPath('priorities.png'), fullPage: true })
    await page.getByRole('button', { name: 'Reset' }).click()
    await expect(ranked.first()).toContainText('Stronger seat ventilation')
    await noOverflow(page)
    await noViolations(page)
  })

  test('an empty register points to the research chat', async ({ page }) => {
    await mock(page, [])
    await page.goto('/#requirements')
    await expect(page.getByText('No requirements yet')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Start a research request' })).toBeVisible()
    await noViolations(page)
  })
})

test.describe('tracking and dossiers', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('check for evidence, see what changed and mark it reviewed', async ({ page }) => {
    const flagged = req(1, 'Stronger seat ventilation', 'tracked', null, { tracked_at: NOW, flags: [{ flag_type: 'contradicting', reason: 'n-1 reads as a praise while the existing evidence reads as a gap.', detected_at: NOW, citations: [{ finding_id: 'n-1', source: 'G60_feedback.xlsx', locator: 'row 9' }] }] })
    const calm = req(2, 'Wireless charging pad', 'tracked', null, { tracked_at: NOW })
    await page.route('**/api/conversations', (r) => json(r, []))
    await page.route('**/api/tracking', (r) => json(r, { requirements: [flagged, calm], last_checked: NOW }))
    await page.route('**/api/tracking/check', (r) => json(r, { checked: 2, summary: 's', flags: [{ flag_type: 'contradicting', requirement_code: 'R-0001', reason: 'x' }], skipped: [], errors: [] }))
    await page.goto('/#tracking')
    const t = page.getByTestId('tracking')
    await expect(t.getByRole('article', { name: /Stronger seat ventilation/ })).toContainText('1 to review')
    await expect(t.getByRole('article', { name: /Wireless charging pad/ })).toContainText('No change')
    await expect(t.getByText('1 requirement needs your attention.')).toBeVisible()
    await t.getByRole('button', { name: 'Check for new evidence' }).click()
    await expect(t.getByRole('status')).toContainText('Checked 2 requirements: 1 change found.')
    await page.screenshot({ path: test.info().outputPath('tracking.png'), fullPage: true })
    await noOverflow(page)
    await noViolations(page)
  })

  test('nothing tracked yet explains how to start', async ({ page }) => {
    await page.route('**/api/conversations', (r) => json(r, []))
    await page.route('**/api/tracking', (r) => json(r, { requirements: [], last_checked: null }))
    await page.goto('/#tracking')
    await expect(page.getByText('Nothing is tracked yet')).toBeVisible()
    await noViolations(page)
  })

  test('a dossier is readable with its sources', async ({ page }) => {
    await page.route('**/api/conversations', (r) => json(r, []))
    await page.route('**/api/dossiers', (r) => json(r, [{ run_id: 'r1', conversation_id: 'c1', title: 'Seat ventilation for the G60', vehicle_line: 'G60', market: 'US', created_at: NOW, dossier: '# Dossier\n- Ventilation is weak [f1]', findings: [{ id: 'f1', text: 'weak', citations: [{ kind: 'feedback', id: 'e1', file: 'G60_feedback.xlsx', locator: 'row 12', quote: 'weak' }] }] }]))
    await page.goto('/#dossiers')
    const d = page.getByTestId('dossiers')
    await expect(d.getByRole('article', { name: 'Dossier' })).toContainText('Ventilation is weak')
    await expect(d.getByRole('button', { name: /Source 1/ })).toBeVisible()
    await page.screenshot({ path: test.info().outputPath('dossier.png'), fullPage: true })
    await noOverflow(page)
    await noViolations(page)
  })
})
