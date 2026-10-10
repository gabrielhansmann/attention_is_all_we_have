import { test, expect, type Page } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'
import { config, emptySnapshot, json, navigate } from './support'
const require = createRequire(import.meta.url)
const token = 'mock-auth-token'
const user = { id:'auth-test-user', email:'pm@example.test', display_name:'Stored Manager', role:'pm' }

async function mockBackend(page: Page, expired: () => boolean = () => false) {
  const log = { logins: [] as unknown[], loggedOut:false, meCalls:0, workspaceCalls:0, sourceTokens:[] as (string | undefined)[] }
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/login') {
      const body = route.request().postDataJSON(); log.logins.push(body)
      return body.password === 'long test passphrase' ? json(route, { token, expires_at:'2026-10-11T12:00:00Z', user }) : json(route, { detail:'invalid email or password' }, 401)
    }
    if (path === '/api/auth/logout') { log.loggedOut = route.request().headers().authorization === `Bearer ${token}`; return route.fulfill({ status:204 }) }
    if (route.request().headers().authorization !== `Bearer ${token}` || expired()) return json(route, { detail:'not authenticated' }, 401)
    if (path === '/api/auth/me') { log.meCalls++; return json(route, user) }
    if (path === '/api/workspace/config') return json(route, config)
    if (path === '/api/workspace') { log.workspaceCalls++; return json(route, emptySnapshot()) }
    if (path === '/api/evidence/filters') return json(route, { lines:['G60'], markets:[], domains:[], polarities:[], powertrains:[] })
    if (path === '/api/evidence/stats') return json(route, { group_by:'market_code', total:0, rows:[] })
    if (path === '/api/evidence/coverage') return json(route, { sales_year:null, total_feedback:0, options_by_line:{}, cells:[] })
    if (path === '/api/sources') { log.sourceTokens.push(route.request().headers().authorization); return json(route, []) }
    return json(route, { detail:'Unmocked test request' }, 503)
  })
  return log
}
async function signIn(page: Page, password = 'long test passphrase') {
  await page.getByLabel('Email', { exact:true }).fill('pm@example.test')
  await page.getByLabel('Password', { exact:true }).fill(password)
  await page.getByRole('button', { name:'Sign in', exact:true }).click()
}

test('all workspace views require sign-in and request data with the issued token', async ({ page }) => {
  const log = await mockBackend(page)
  await page.goto('/#evidence')
  await expect(page.getByRole('heading', { name:'Sign in to your workspace' })).toBeVisible()
  expect(log.workspaceCalls).toBe(0)
  await page.addScriptTag({ path:require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe:typeof axe }).axe.run(document, { runOnly:{ type:'tag', values:['wcag2a','wcag2aa','wcag21aa'] } })).violations)
  expect(violations).toEqual([])
  await signIn(page, 'wrong test password')
  await expect(page.getByRole('alert')).toHaveText('invalid email or password')
  await expect(page.getByLabel('Password', { exact:true })).toHaveValue('wrong test password')
  await signIn(page)
  await expect(page.getByTestId('live-library')).toBeVisible()
  await expect(page.getByText('Signed in as Stored Manager')).toBeVisible()
  expect(log.sourceTokens.at(-1)).toBe(`Bearer ${token}`)
  expect(await page.evaluate(() => localStorage.getItem('bmw-api-token'))).toBeNull()
})

test('reload restores identity and sign-out revokes the backend session', async ({ page }) => {
  const log = await mockBackend(page)
  await page.goto('/')
  await signIn(page)
  await expect(page.getByText('Signed in as Stored Manager')).toBeVisible()
  await page.reload()
  await expect(page.getByText('Signed in as Stored Manager')).toBeVisible()
  expect(log.meCalls).toBeGreaterThan(0)
  await page.getByRole('button', { name:'Sign out', exact:true }).click()
  await expect(page.getByRole('heading', { name:'Sign in to your workspace' })).toBeVisible()
  expect(log.loggedOut).toBe(true)
  expect(await page.evaluate(() => sessionStorage.getItem('bmw-api-token'))).toBeNull()
})

test('an expired session clears all workspace views and asks for sign-in', async ({ page }) => {
  let expired = false
  await mockBackend(page, () => expired)
  await page.goto('/')
  await signIn(page)
  await expect(page.getByRole('heading', { name:'Build what comes next.' })).toBeVisible()
  expired = true
  await navigate(page, 'Requirements')
  await expect(page.getByRole('heading', { name:'Sign in to your workspace' })).toBeVisible()
  await expect(page.getByRole('table', { name:'Requirement portfolio' })).toHaveCount(0)
})
