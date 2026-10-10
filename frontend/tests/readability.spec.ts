import { test, expect } from '@playwright/test'
import { NOW, closeMenu, json, noOverflow, noViolations, openMenu, withSession } from './helpers'

// Every backend call is mocked: nothing reaches a real backend or database.
const conversation = { id: 'c1', title: 'US G60 infotainment', vehicle_line: 'G60', market_code: 'US', status: 'active', created_at: NOW, updated_at: NOW }
const msg = (seq: number, role: string, kind: string, content: string, payload = {}, step_id: string | null = null) =>
  ({ id: `m${seq}`, seq, conversation_id: 'c1', role, kind, run_id: 'r1', step_id, content, payload, created_at: NOW })

const summary = [
  'Requirements Drafting Agent looked at 3 accepted cluster(s) with 9 linked finding(s) for G60 / US and drafted 2 requirement(s), each at status draft.',
  '',
  'Draft requirements:',
  '- Reliable voice assistant [Infotainment; evidence Verified; cluster: Voice control]',
  '  - Description: Voice commands succeed on the first try (G60_feedback.xlsx, row 12)',
  '  - Metric: 90% first-try success',
  '- Shallower menus [Infotainment; evidence Indicative; cluster: Menu depth]',
  '  - Description: Common functions are reachable in two taps',
  '',
  'Confidence and gaps:',
  '- Menu depth rests on a single source.',
].join('\n')

const dossier = [
  '# Research dossier: voice assistant complaints',
  '',
  'Scope: G60 / US. Compiled 2026-10-13 by the Documentation Agent from 2 accepted step(s) of 2.',
  '',
  '## Accepted steps',
  '',
  '1. **Customer Feedback Agent**: Owners find the voice assistant unreliable.',
  '2. **Clustering Agent**, accepted by orchestrator: Two themes found.',
  '',
  '## Customer needs',
  '',
  '- Owners find the voice assistant unreliable. [f1]',
  '',
  '## Audit trail',
  '',
  '| Timestamp | Actor | Action | Rationale |',
  '|---|---|---|---|',
  '| 2026-10-13 09:00 | orchestrator | step_started | asks what owners say |',
  '',
  '## Sources',
  '',
  '- [f1] G60_feedback.xlsx, row 12',
].join('\n')

const finding = { id: 'f1', text: 'Voice assistant unreliable.', citations: [{ kind: 'feedback', id: 'e1', file: 'G60_feedback.xlsx', locator: 'row 12', quote: 'It never understands me' }] }
const thread = [
  msg(1, 'pm', 'request', 'What do US G60 owners dislike most about the infotainment?'),
  msg(2, 'orchestrator', 'system_note', 'Calling Requirements Drafting Agent: themes are ready.', { decision: { agent: 'Requirements Drafting Agent', reason: 'themes are ready.', position: 3 } }, 's1'),
  msg(3, 'agent', 'step_card', summary, { agent: 'Requirements Drafting Agent', failed: false, output: { findings: [finding] } }, 's1'),
  msg(4, 'orchestrator', 'final_result', dossier, { requirements: 2, coverage_gaps: [] }),
]

test.describe('readable answers', () => {
  test.beforeEach(async ({ page }) => { await withSession(page) })

  test('agent summaries and the result are structured, not a wall of text', async ({ page }) => {
    await page.route('**/api/conversations', (r) => json(r, [conversation]))
    await page.route('**/api/conversations/c1', (r) => json(r, { conversation, messages: thread, runs: [{ id: 'r1', conversation_id: 'c1', vehicle_line: 'G60', market: 'US', query_text: 'q', status: 'completed', created_at: NOW, steps: [] }] }))
    await page.goto('/')
    await openMenu(page)
    await page.locator('[data-testid=sidebar]:visible').getByText('US G60 infotainment').click()
    await closeMenu(page)
    const live = page.getByTestId('live-research')
    const card = live.getByRole('article', { name: 'Requirements Drafting Agent result' })
    await expect(live.getByText('Step 3: Requirements Drafting Agent')).toBeVisible()
    await expect(card.getByText('Requirements', { exact: true })).toBeVisible()
    // the detail is behind a toggle, and opens as real lists
    await expect(card.getByText('Reliable voice assistant')).toBeHidden()
    await card.getByText('Show full summary').click()
    await expect(card.getByRole('listitem').filter({ hasText: 'Reliable voice assistant' })).toBeVisible()
    await expect(card.getByRole('heading', { name: 'Draft requirements' })).toBeVisible()

    // the result: ordered list stays closed with the audit trail, and next steps are spelled out
    const result = live.getByText('Research finished').locator('..').locator('..')
    await expect(result.getByRole('heading', { name: 'Customer needs' })).toBeVisible()
    await expect(result.getByRole('table')).toBeHidden()
    await result.getByText('Audit trail').click()
    await expect(result.getByRole('columnheader', { name: 'Rationale' })).toBeVisible()
    await expect(result.getByRole('link', { name: 'Review 2 requirements' })).toBeVisible()
    await expect(result.getByRole('link', { name: 'Open dossier' })).toBeVisible()
    await page.screenshot({ path: test.info().outputPath('chat.png'), fullPage: true })
    await noOverflow(page)
    await noViolations(page)
  })

  test('each process page says what the step is and what to do next', async ({ page }) => {
    await page.route('**/api/conversations', (r) => json(r, []))
    await page.route('**/api/requirements', (r) => json(r, { requirements: [], counts: {} }))
    await page.route('**/api/tracking', (r) => json(r, { requirements: [], last_checked: null }))
    await page.route('**/api/dossiers', (r) => json(r, [{ run_id: 'r1', conversation_id: 'c1', title: 'Voice assistant', vehicle_line: 'G60', market: 'US', created_at: NOW, dossier, findings: [finding] }]))

    await page.goto('/#requirements')
    const guide = page.getByTestId('step-guide')
    await expect(guide.getByRole('link', { name: /Track/ })).toBeVisible()

    await page.goto('/#tracking')
    await expect(page.getByTestId('step-guide').getByRole('link', { name: /Document/ })).toBeVisible()

    await page.goto('/#dossiers')
    await expect(page.getByTestId('step-guide')).toContainText('1 dossier')
    const article = page.getByRole('article', { name: 'Dossier' })
    await expect(article.getByRole('heading', { name: 'Customer needs' })).toBeVisible()
    await expect(article.getByRole('table')).toBeHidden()
    await page.screenshot({ path: test.info().outputPath('dossier.png'), fullPage: true })
    await noOverflow(page)
    await noViolations(page)
  })
})
