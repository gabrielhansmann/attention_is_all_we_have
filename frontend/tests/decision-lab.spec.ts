import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import type axe from 'axe-core'
import { createWorkspace, defaultWeights, storageKey } from '../src/data'

const require = createRequire(import.meta.url)
test.beforeEach(async ({ page }) => { await page.goto('/#decision-lab') })

test('scenario previews explain shortlist movement without changing saved priorities', async ({ page }, testInfo) => {
  await expect(page.getByRole('heading', { name: 'Test the trade-offs.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Apply scenario weights', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: /Growth focused/ }).click()
  const entering = page.locator('[data-requirement-id="D-004"]')
  const leaving = page.locator('[data-requirement-id="D-003"]')
  await expect(entering).toContainText('Enters')
  await expect(leaving).toContainText('Leaves')
  await expect(entering).toContainText('84% confidence')
  expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).weights, storageKey)).toEqual(defaultWeights)
  await entering.getByText('Explain score and evidence', { exact: true }).click()
  await expect(entering.getByRole('cell', { name: '+0.4620', exact: true })).toBeVisible()
  await entering.getByRole('button', { name: /G60_OptionList.PDF/ }).click()
  await expect(page.getByRole('dialog')).toContainText('Page 18, equipment overview')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Reset to saved weights', exact: true }).click()
  await expect(entering).toContainText('Outside shortlist')
  await page.getByRole('button', { name: /Customer first/ }).click()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.locator('#main-content').focus()
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.screenshot({ path: `/tmp/attention-decision-lab-${testInfo.project.name}-viewport.png` })
  await page.screenshot({ path: `/tmp/attention-decision-lab-${testInfo.project.name}.png`, fullPage: true })
})

test('sliders work with the keyboard and handle a completely effort-driven scenario', async ({ page }) => {
  const relevance = page.getByRole('slider', { name: 'Customer relevance', exact: true })
  await relevance.focus(); await page.keyboard.press('ArrowRight')
  await expect(relevance).toHaveValue('41')
  const weights = await page.getByRole('slider').evaluateAll(elements => elements.map(element => Number((element as HTMLInputElement).value)))
  expect(weights.reduce((sum, value) => sum + value, 0)).toBe(100)
  const effort = page.getByRole('slider', { name: 'Effort penalty', exact: true })
  await effort.focus(); await page.keyboard.press('End')
  await expect(effort).toHaveValue('100')
  await expect(page.getByRole('img', { name: /Predictable rapid charging: saved score/ })).toHaveAttribute('aria-label', /scenario score -0.1500/)
  await page.getByLabel('Shortlist size', { exact: true }).selectOption('1')
  await expect(page.locator('.lab-shortlisted')).toHaveCount(1)
  await expect(page.locator('.lab-shortlisted')).toContainText('Predictable rapid charging')
})

test('applying a scenario requires a reason, persists the weights, and leaves evidence intact', async ({ page }) => {
  await page.getByRole('button', { name: /Growth focused/ }).click()
  await page.getByRole('button', { name: 'Apply scenario weights', exact: true }).click()
  await page.getByRole('button', { name: 'Save scenario weights', exact: true }).click()
  await expect(page.getByLabel('Reason for applying this scenario')).toBeFocused()
  await page.getByLabel('Reason for applying this scenario').fill('Explore business opportunity while retaining the cited evidence.')
  await page.getByRole('button', { name: 'Save scenario weights', exact: true }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)
  const saved = await page.evaluate(key => JSON.parse(localStorage.getItem(key)!), storageKey)
  expect(saved.weights).toEqual({ relevance: 20, business: 55, fit: 20, effort: 5 })
  expect(saved.requirements).toEqual(createWorkspace().requirements)
  expect(saved.audits[0].title).toBe('Decision Lab weights applied')
  expect(saved.audits[0].detail).toContain('entering D-004; leaving D-003')
  await page.reload()
  await expect(page.getByRole('slider', { name: 'Business signal', exact: true })).toHaveValue('55')
  await expect(page.getByRole('button', { name: 'Apply scenario weights', exact: true })).toBeDisabled()
})

test('a scenario export carries the comparison, evidence locators, and caveats', async ({ page }) => {
  await page.getByRole('button', { name: /Growth focused/ }).click()
  const downloading = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export scenario brief', exact: true }).click()
  const download = await downloading
  expect(download.suggestedFilename()).toBe('decision-lab-G60-EU.md')
  const brief = await readFile((await download.path())!, 'utf8')
  expect(brief).toContain('0.7225 | 0.8785')
  expect(brief).toContain('G60_OptionList.PDF (Page 18, equipment overview)')
  expect(brief).toContain('Engineering feasibility and customer validation are still required.')
  expect(brief).toContain('They are not probabilities')
})

test('scope changes reset the preview and empty portfolios have an actionable state', async ({ page }) => {
  await page.getByRole('button', { name: /Growth focused/ }).click()
  await page.getByLabel('Market', { exact: true }).selectOption('CN')
  await expect(page.locator('.lab-ranked-item')).toHaveCount(2)
  await expect(page.getByRole('slider', { name: 'Business signal', exact: true })).toHaveValue('25')
  await expect(page.getByText('2 shortlisted requirements need more evidence.')).toBeVisible()
  await page.evaluate(key => {
    const state = JSON.parse(localStorage.getItem(key)!)
    state.requirements = []
    localStorage.setItem(key, JSON.stringify(state))
  }, storageKey)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'No active requirements in this scope' })).toBeVisible()
  await expect(page.getByLabel('Shortlist size', { exact: true })).toBeDisabled()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('the lab and expanded score calculation pass automated accessibility checks', async ({ page }) => {
  await page.getByRole('button', { name: /Growth focused/ }).click()
  await page.locator('[data-requirement-id="D-004"]').getByText('Explain score and evidence', { exact: true }).click()
  await page.addScriptTag({ path: require.resolve('axe-core/axe.min.js') })
  const violations = await page.evaluate(async () => (await (window as unknown as { axe: typeof axe }).axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations)
  expect(violations).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
