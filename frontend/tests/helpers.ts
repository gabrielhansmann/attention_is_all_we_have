import { expect, type Page, type Route } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'

const require = createRequire(import.meta.url)
export const NOW = '2026-10-13T09:00:00Z'
export const TOKEN = 'tok-1'
export const PASSWORD = 'a long enough passphrase'
export const user = { id: 'u1', email: 'pat.manager@example.com', display_name: 'Pat Manager', role: 'pm' }

export const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, json: body })
export const authed = (route: Route) => route.request().headers().authorization === `Bearer ${TOKEN}`

export async function noViolations(page: Page) {
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () =>
    (await (window as unknown as { axe: typeof axe }).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } }))
      .violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.html.slice(0, 160)) })))
  expect(violations).toEqual([])
}

export async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

/** Skip the sign-in form: the token is what the app keeps after a login. */
export async function withSession(page: Page) {
  await page.addInitScript(([k, v]) => window.sessionStorage.setItem(k, v), ['bmw-api-token', TOKEN])
  await page.route('**/api/auth/me', (r) => json(r, user))
  await page.route('**/api/health', (r) => json(r, { status: 'ok', db: 'ok', openai_key: true, version: 'test' }))
}

/** The sidebar is always visible on desktop and lives in a sheet on small screens. */
export async function openMenu(page: Page) {
  const button = page.getByRole('button', { name: 'Open menu' })
  if (await button.isVisible()) {
    await button.click()
    await expect(page.getByRole('dialog')).toBeVisible()
  }
}
export async function closeMenu(page: Page) {
  // A CSS locator: role queries skip content hidden by the open sheet.
  if (!(await page.locator('button[aria-label="Open menu"]').isVisible())) return
  // Escape is ignored until the sheet has finished opening, so press it again until the sheet is gone.
  await expect(async () => {
    await page.keyboard.press('Escape')
    await expect(page.locator('[data-slot=sheet-content]')).toHaveCount(0, { timeout: 1000 })
  }).toPass()
  await expect(page.locator('#root')).not.toHaveAttribute('aria-hidden', 'true')
}
