import { test, expect, type Page } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'
import { mockWorkspace } from './support'

const require = createRequire(import.meta.url)
const date = '2026-10-10T12:00:00Z'
const agent = 'Customer Feedback Agent'
const conversation = { id: 'c1', title: 'Seat comfort', status: 'active', vehicle_line: 'G60', market_code: 'US', created_at: date, updated_at: date }

async function enterLive(page: Page) {
  await page.goto('/#research')
  await page.getByLabel('Research request', { exact: true }).fill('Research seat comfort in the US')
  await page.getByRole('button', { name: 'Plan request', exact: true }).click()
}

async function setup(page: Page, failed = false) {
  let status = 'planned'
  let attempt = 1
  let seq = 2
  let summary = failed ? 'Agent could not finish. Nothing was produced.' : 'Seats need faster ventilation (feedback.xlsx, sheet Feedback, row 7).'
  let didFail = failed
  const calls: { action: string; body: Record<string, unknown> }[] = []
  const messages: Record<string, unknown>[] = [
    { id: 'm1', seq: 1, conversation_id: 'c1', role: 'pm', kind: 'request', content: 'Research seat comfort', payload: {}, run_id: null, step_id: null, created_at: date },
    { id: 'm2', seq: 2, conversation_id: 'c1', role: 'orchestrator', kind: 'plan', content: 'Plan', payload: { steps: [{ agent, available: true, position: 1, stage: 1 }] }, run_id: 'r1', step_id: null, created_at: date },
  ]
  function card() {
    messages.push({ id: `m${++seq}`, seq, conversation_id: 'c1', role: 'agent', kind: 'step_card', content: summary,
      payload: { agent, attempt, failed: didFail, critic: { dropped: [{ text: 'unsupported' }], downgrades: [] } }, run_id: 'r1', step_id: 's1', created_at: date })
  }
  function detail() {
    return { conversation, messages, runs: [{ id: 'r1', conversation_id: 'c1', vehicle_line: 'G60', market: 'US', query_text: 'q',
      status: status === 'accepted' ? 'completed' : status === 'aborted' ? 'aborted' : 'in_progress', created_at: date,
      steps: [{ id: 's1', position: 1, agent_name: agent, stage: 1, status: status === 'aborted' ? 'rejected' : status,
        available: true, planned_by: 'orchestrator', plan_reason: 'Customer evidence', attempt, human_readable_summary: summary }] }] }
  }
  await mockWorkspace(page)
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    let response: unknown = {}
    if (path === '/api/health') response = { status: 'ok', db: 'ok', openai_key: true, version: 'test' }
    else if (path === '/api/agents') response = [{ name: agent, stage: 1, description: 'Customer evidence', available: true }]
    else if (path === '/api/conversations') response = method === 'POST' ? detail() : []
    else if (path === '/api/conversations/c1') {
      if (status === 'running') { status = 'awaiting_review'; card() }
      response = detail()
    } else if (path === '/api/runs/r1/start') {
      calls.push({ action: 'start', body: {} }); status = 'running'; response = { run: detail().runs[0], messages: [] }
    } else if (path.startsWith('/api/steps/s1/')) {
      const action = path.split('/').at(-1)!
      const body = route.request().postDataJSON()
      calls.push({ action, body })
      if (action === 'edit') { summary = body.summary; card() }
      if (action === 'retry') { status = 'running'; attempt++; didFail = false }
      if (action === 'accept' || action === 'reject') {
        status = action === 'accept' || body.proceed ? 'accepted' : 'aborted'
        if (status === 'accepted') messages.push({ id: `m${++seq}`, seq, conversation_id: 'c1', role: 'orchestrator', kind: 'final_result',
          content: action === 'reject' ? 'No accepted output. Coverage gaps: Customer Feedback Agent.' : 'Final cited research result.', payload: {}, run_id: 'r1', step_id: null, created_at: date })
      }
      response = { messages: [], run: detail().runs[0] }
    } else return route.fallback()
    await route.fulfill({ json: response })
  })
  return calls
}

test('live plan starts, reviews with a reason, edits, and completes only after acceptance', async ({ page }, testInfo) => {
  const calls = await setup(page)
  await enterLive(page)
  const live = page.getByTestId('live-research')
  await expect(live.getByRole('button', { name: 'Accept and continue' })).toHaveCount(0)
  await live.getByRole('button', { name: 'Start research', exact: true }).click()
  await expect(live.getByRole('button', { name: 'Edit plan' })).toHaveCount(0)
  await expect(live.getByText('Critic removed 1 unsupported claims.')).toBeVisible()
  await expect(live.getByRole('button', { name: 'Accept and continue' })).toBeDisabled()
  await live.getByLabel('Review reason or steering note').fill('Tighten the wording without changing evidence')
  await live.getByRole('button', { name: 'Edit summary' }).click()
  await live.getByLabel('Edited summary').fill('Revised comfort summary, feedback.xlsx row 7.')
  await live.getByRole('button', { name: 'Save summary' }).click()
  await expect(live.getByText('Revised comfort summary, feedback.xlsx row 7.', { exact: true })).toBeVisible()
  await live.getByLabel('Review reason or steering note').fill('Evidence supports this finding')
  await page.screenshot({ path: `/tmp/attention-live-review-${testInfo.project.name}.png`, fullPage: true })
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe: typeof axe }).axe.run(document,
    { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations)
  expect(violations).toEqual([])
  await live.getByRole('button', { name: 'Accept and continue' }).click()
  await expect(live.getByText('Final cited research result.', { exact: true })).toBeVisible()
  await expect(live.getByRole('button', { name: 'Accept and continue' })).toHaveCount(0)
  expect(calls.map(c => c.action)).toEqual(['start', 'edit', 'accept'])
  expect(calls.at(-1)?.body.note).toBe('Evidence supports this finding')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('failed live output can be retried and rejected with an explicit abort choice', async ({ page }) => {
  const calls = await setup(page, true)
  await enterLive(page)
  const live = page.getByTestId('live-research')
  await live.getByRole('button', { name: 'Start research', exact: true }).click()
  await live.getByLabel('Review reason or steering note').fill('Retry using the source evidence')
  await expect(live.getByRole('button', { name: 'Accept and continue' })).toBeDisabled()
  await expect(live.getByRole('button', { name: 'Edit summary' })).toBeDisabled()
  await live.getByRole('button', { name: 'Retry', exact: true }).click()
  await live.getByLabel('Review reason or steering note').fill('Evidence is insufficient for this request')
  await live.getByRole('button', { name: 'Reject', exact: true }).click()
  expect(calls.some(c => c.action === 'reject')).toBe(false)
  await live.getByRole('button', { name: 'Abort research', exact: true }).click()
  await expect(live.getByText('Research aborted', { exact: true })).toBeVisible()
  expect(calls.at(-1)).toEqual({ action: 'reject', body: { note: 'Evidence is insufficient for this request', proceed: false } })
})
