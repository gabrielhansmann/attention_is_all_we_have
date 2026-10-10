import { test, expect, type Page, type Route } from '@playwright/test'
import { PASSWORD, TOKEN, NOW, authed, closeMenu, json, noViolations, openMenu, user } from './helpers'

// The backend is fully mocked and enforces the token, so these tests check what the browser really sends.
interface Log { sourcesAuth: (string | undefined)[]; logins: { email: string; password: string }[]; loggedOut: boolean; meCalls: number }

async function mockBackend(page: Page, opts: { sessionExpired?: () => boolean } = {}): Promise<Log> {
  await page.route('**/api/**', (r) => json(r, { detail: 'API response not provided by this test' }, 404))
  const log: Log = { sourcesAuth: [], logins: [], loggedOut: false, meCalls: 0 }
  const guarded = (body: unknown) => (route: Route) =>
    authed(route) && !opts.sessionExpired?.() ? json(route, body) : json(route, { detail: 'not authenticated' }, 401)
  await page.route('**/api/conversations', guarded([]))
  await page.route('**/api/health', (r) => json(r, { status: 'ok', db: 'ok', openai_key: true, version: 'test' }))
  await page.route('**/api/evidence/coverage', guarded({ total_feedback: 1, options_by_line: { G60: 1 }, cells: [{ line: 'G60', market: 'US', feedback: 500, study_cells: 3, sales_2025: 10 }] }))
  await page.route('**/api/sources', (r) => {
    log.sourcesAuth.push(r.request().headers().authorization)
    return guarded([{ id: 'a', file: 'G60_feedback_hackathon.xlsx', type: 'internal_xlsx', family: 'Customer feedback', vehicle_line: 'G60', market: null, title: null, retrieved_at: NOW, trust_tier: null, counts: { feedback: 5005, pdf_chunks: 0, options: 0, study_cells: 0, sales_rows: 0 } }])(r)
  })
  await page.route('**/api/sources/graph', guarded({ links: [{ source_id: 'a', line: 'G60', market: 'US', rows: 5005 }] }))
  await page.route('**/api/sources/web-research', guarded([]))
  await page.route('**/api/auth/login', (r) => {
    const body = r.request().postDataJSON()
    log.logins.push(body)
    return body.password === PASSWORD ? json(r, { token: TOKEN, expires_at: NOW, user }) : json(r, { detail: 'invalid email or password' }, 401)
  })
  await page.route('**/api/auth/me', (r) => { log.meCalls++; return guarded(user)(r) })
  await page.route('**/api/auth/logout', (r) => { log.loggedOut = authed(r); return r.fulfill({ status: 204 }) })
  return log
}
async function signIn(page: Page, password = PASSWORD) {
  await page.getByLabel('Email', { exact: true }).fill('Pat.Manager@example.com')
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
}

test('nothing is shown before signing in, and the token is sent afterwards', async ({ page }) => {
  const log = await mockBackend(page)
  await page.goto('/#sources')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Main' })).toHaveCount(0)
  expect(log.sourcesAuth).toEqual([])                                           // no data request without a session
  await noViolations(page)

  await signIn(page, 'wrong password')
  await expect(page.getByRole('alert')).toHaveText('invalid email or password')
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue('wrong password')   // kept so it can be fixed

  await signIn(page)
  await expect(page.getByTestId('source-graph')).toBeVisible()
  await openMenu(page)
  await expect(page.getByRole('button', { name: /Pat Manager/ })).toBeVisible()
  await closeMenu(page)
  expect(log.logins.at(-1)).toEqual({ email: 'Pat.Manager@example.com', password: PASSWORD })
  expect(log.sourcesAuth.at(-1)).toBe(`Bearer ${TOKEN}`)
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBe(TOKEN)
  expect(await page.evaluate(() => window.localStorage.length)).toBe(0)          // nothing in long-lived storage
})

test('a reload keeps the session, and signing out revokes it', async ({ page }) => {
  const log = await mockBackend(page)
  await page.goto('/#sources')
  await signIn(page)
  await openMenu(page)
  await expect(page.getByRole('button', { name: /Pat Manager/ })).toBeVisible()
  await closeMenu(page)

  await page.reload()
  await expect(page.getByTestId('source-graph')).toBeVisible()   // no second sign-in
  expect(log.meCalls).toBeGreaterThan(0)

  await openMenu(page)
  await page.getByRole('button', { name: /Pat Manager/ }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect(log.loggedOut).toBe(true)
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBeNull()
})

test('a session that expires while the page is open sends the user back to sign in', async ({ page }) => {
  let expired = false
  await mockBackend(page, { sessionExpired: () => expired })
  await page.goto('/#sources')
  await signIn(page)
  await expect(page.getByTestId('source-graph')).toBeVisible()
  expired = true
  await openMenu(page)
  await page.getByRole('link', { name: 'Research', exact: true }).click()
  await openMenu(page)
  await page.getByRole('link', { name: 'Sources', exact: true }).click()          // remount: requests now return 401
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  expect(await page.evaluate(() => window.sessionStorage.getItem('bmw-api-token'))).toBeNull()
})
