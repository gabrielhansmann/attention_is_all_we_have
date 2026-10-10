import { test, expect, type Page, type Route } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'

// The backend is fully mocked: the mock enforces the token, so these tests check what the browser really sends.
const require = createRequire(import.meta.url)
const TOKEN = 'tok-1'
const NOW = '2026-10-13T09:00:00Z'
const user = { id: 'u1', email: 'pat.manager@example.com', display_name: 'Pat Manager', role: 'pm' }

async function navigate(page: Page, name: string) {
  const link = page.getByRole('link', { name, exact: true })
  if (!(await link.count()) || !(await link.first().isVisible())) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('link', { name, exact: true }).click()
}
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })
const authed = (route: Route) => route.request().headers().authorization === `Bearer ${TOKEN}`

interface Log { sourcesAuth: (string | undefined)[]; logins: { email: string; password: string }[]; loggedOut: boolean; meCalls: number; authCalls: number }

async function mockBackend(page: Page, opts: { sessionExpired?: () => boolean } = {}): Promise<Log> {
  const log: Log = { sourcesAuth: [], logins: [], loggedOut: false, meCalls: 0, authCalls: 0 }
  const guarded = (body: unknown) => (route: Route) =>
    authed(route) && !opts.sessionExpired?.() ? json(route, body) : json(route, { detail: 'not authenticated' }, 401)
  await page.route('**/api/health', r => json(r, { status: 'ok', db: 'ok', openai_key: true, version: 'test' }))
  await page.route('**/api/evidence/filters', guarded({ lines: ['G60'], markets: [], domains: [], polarities: [], powertrains: [] }))
  await page.route('**/api/evidence/stats?**', guarded({ group_by: 'market_code', total: 0, rows: [] }))
  await page.route('**/api/evidence/coverage', guarded({ total_feedback: 1, options_by_line: { G60: 1 }, cells: [{ line: 'G60', market: 'US', feedback: 500, study_cells: 3, sales_2025: 10 }] }))
  await page.route('**/api/sources', r => { log.sourcesAuth.push(r.request().headers().authorization); return guarded([{ id: 'a', file: 'G60_feedback_hackathon.xlsx', type: 'internal_xlsx', family: 'Customer feedback', vehicle_line: 'G60', market: null, title: null, retrieved_at: NOW, counts: { feedback: 5005, pdf_chunks: 0, options: 0, study_cells: 0, sales_rows: 0 } }])(r) })
  await page.route('**/api/auth/login', r => {
    const body = r.request().postDataJSON()
    log.logins.push(body)
    log.authCalls++
    return body.password === 'a long enough passphrase'
      ? json(r, { token: TOKEN, expires_at: NOW, user })
      : json(r, { detail: 'invalid email or password' }, 401)
  })
  await page.route('**/api/auth/me', r => { log.meCalls++; log.authCalls++; return guarded(user)(r) })
  await page.route('**/api/auth/logout', r => { log.loggedOut = authed(r); log.authCalls++; return r.fulfill({ status: 204 }) })
  return log
}
async function openLiveLibrary(page: Page) {
  await page.goto('/')
  await navigate(page, 'Evidence library')
  await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
}
async function signIn(page: Page, password = 'a long enough passphrase') {
  await page.getByLabel('Email', { exact: true }).fill('Pat.Manager@example.com')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

test('the sign-in form appears when the backend asks for it, and the token is sent afterwards', async ({ page }) => {
  const log = await mockBackend(page)
  await openLiveLibrary(page)
  await expect(page.getByRole('heading', { name: 'Sign in to use live mode' })).toBeVisible()
  await expect(page.getByTestId('live-library')).toHaveCount(0)              // nothing is shown before signing in

  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe: typeof axe }).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.html.slice(0, 160)) })))
  expect(violations).toEqual([])

  await signIn(page, 'wrong password')
  await expect(page.getByRole('alert')).toHaveText('invalid email or password')
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('wrong password')   // not cleared on failure, so it can be fixed

  await signIn(page)
  await expect(page.getByTestId('live-library').getByRole('table', { name: 'Source files loaded into the evidence store' })).toBeVisible()
  await expect(page.getByText('Signed in as Pat Manager')).toBeVisible()
  expect(log.logins.at(-1)).toEqual({ email: 'Pat.Manager@example.com', password: 'a long enough passphrase' })
  expect(log.sourcesAuth.at(-1)).toBe(`Bearer ${TOKEN}`)
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBe(TOKEN)
  expect(await page.evaluate(() => window.localStorage.getItem('bmw-api-token'))).toBeNull()   // never in long-lived storage
})

test('a reload keeps the session, and signing out revokes it and returns to the form', async ({ page }) => {
  const log = await mockBackend(page)
  await openLiveLibrary(page)
  await signIn(page)
  await expect(page.getByText('Signed in as Pat Manager')).toBeVisible()

  await page.reload()
  await navigate(page, 'Evidence library')
  await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()
  await expect(page.getByTestId('live-library')).toBeVisible()                // no second sign-in
  await expect(page.getByText('Signed in as Pat Manager')).toBeVisible()      // name restored through /auth/me
  expect(log.meCalls).toBeGreaterThan(0)

  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to use live mode' })).toBeVisible()
  expect(log.loggedOut).toBe(true)                                            // the server session was revoked with the token
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBeNull()
})

test('a session that expires while the page is open sends the user back to sign in', async ({ page }) => {
  let expired = false
  await mockBackend(page, { sessionExpired: () => expired })
  await openLiveLibrary(page)
  await signIn(page)
  await expect(page.getByTestId('live-library')).toBeVisible()
  expired = true
  await page.getByRole('button', { name: 'Demo sources', exact: true }).click()
  await page.getByRole('button', { name: 'Browse backend evidence', exact: true }).click()   // remount: requests now return 401
  await expect(page.getByRole('heading', { name: 'Sign in to use live mode' })).toBeVisible()
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBeNull()   // the dead token is dropped
})

test('the offline demo never calls the auth endpoints', async ({ page }) => {
  const log = await mockBackend(page)
  await page.goto('/')
  for (const name of ['Requirements', 'Research', 'Evidence library', 'Reports', 'Overview']) await navigate(page, name)
  expect(log.authCalls).toBe(0)
  await expect(page.getByRole('heading', { name: 'Sign in to use live mode' })).toHaveCount(0)
})
