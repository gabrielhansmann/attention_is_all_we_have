import { test, expect } from '@playwright/test'
import { createRequire } from 'node:module'
import type axe from 'axe-core'
import { emptySnapshot, json, mockWorkspace, navigate, storedRequirement } from './support'
const require = createRequire(import.meta.url)

test('overview uses backend values and ignores old local demo data', async ({ page }, testInfo) => {
  const data = emptySnapshot()
  data.counts = { feedback: 913, study_cells: 27, catalog_options: 1, pending_steps: 2 }
  data.sales = [{ id:'sale-1', vehicle_line:'G60', market_code:'EU', year:2027, volume:12345, is_forecast:false, file:'recorded-sales.xlsx', locator:'sheet Europe, row 6' }, { id:'sale-2', vehicle_line:'G60', market_code:'EU', year:2031, volume:15000, is_forecast:true, file:'recorded-sales.xlsx', locator:'sheet Europe, row 7' }]
  data.options = [{ id:'option-1', vehicle_line:'G60', code:'SA-REAL', name:'Stored equipment item', description:null, standard_variants:2, optional_variants:1, file:'loaded-catalog.pdf', locator:'page 8' }]
  await mockWorkspace(page, { snapshot: () => data })
  await page.addInitScript(() => localStorage.setItem('bmw-product-intelligence-v1', JSON.stringify({ version:1, requirements:[{ title:'OLD FAKE REQUIREMENT' }] })))
  await page.goto('/')
  await expect(page.getByText('913', { exact:true })).toBeVisible()
  await expect(page.getByText('12,345', { exact:true })).toBeVisible()
  await expect(page.getByText('Forecast', { exact:true })).toBeVisible()
  await expect(page.getByText('SA-REAL: Stored equipment item')).toBeVisible()
  await expect(page.getByText('OLD FAKE REQUIREMENT')).toHaveCount(0)
  await expect(page.getByText('Illustrative metrics')).toHaveCount(0)
  await page.getByLabel('Vehicle line', { exact:true }).selectOption('G60')
  await expect(page.getByLabel('Vehicle line', { exact:true })).toHaveValue('G60')
  await page.getByLabel('Market', { exact:true }).selectOption('EU')
  await expect(page.getByLabel('Market', { exact:true })).toHaveValue('EU')
  await expect(page.getByRole('heading', { name:'Build what comes next.' })).toBeVisible()
  await page.screenshot({ path:`/tmp/attention-real-workspace-${testInfo.project.name}.png`, fullPage:true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('empty requirements and missing scores stay empty instead of being estimated', async ({ page }) => {
  const data = emptySnapshot()
  await mockWorkspace(page, { snapshot:() => data })
  await page.goto('/#requirements')
  await expect(page.getByRole('heading', { name:'No persisted requirements in this scope' })).toBeVisible()
  await expect(page.getByRole('button', { name:'Export portfolio' })).toBeDisabled()
  data.requirements = [storedRequirement()]
  await page.getByRole('button', { name:'Refresh data' }).click()
  await expect(page.getByRole('button', { name:'Stored climate requirement', exact:true })).toBeVisible()
  await expect(page.getByText('Not scored', { exact:true })).toHaveCount(2)
  data.requirements[0].score = 0; data.requirements[0].confidence = 0
  await page.getByRole('button', { name:'Refresh data' }).click()
  await expect(page.getByText('0%', { exact:true })).toBeVisible()
})

test('requirement reviews send reasons to the backend and refresh the persisted history', async ({ page }) => {
  const data = emptySnapshot(); data.requirements = [storedRequirement()]
  const calls: unknown[] = []
  await mockWorkspace(page, { snapshot:() => data })
  await page.route('**/api/requirements/*/status', route => {
    const body = route.request().postDataJSON(); calls.push(body)
    data.requirements[0].status = body.status; data.requirements[0].allowed_statuses = ['challenged','superseded']
    data.audits = [{ id:'a1', entity_type:'requirement', entity_id:data.requirements[0].id, action:'requirement_status_changed', actor:'pm@example.test', rationale:body.reason, timestamp:data.generated_at, before:{ status:'pm_review' }, after:{ status:body.status } }]
    return json(route, { id:data.requirements[0].id, status:body.status })
  })
  await page.goto('/#requirements')
  await page.getByRole('button', { name:'Stored climate requirement', exact:true }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByText('sheet Feedback, row 81')).toBeVisible()
  await expect(dialog.getByRole('button', { name:'Move to Tracked' })).toBeDisabled()
  await dialog.getByLabel('Review reason').fill('The original evidence supports this direction')
  await dialog.getByRole('button', { name:'Move to Tracked' }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('table').getByText('Tracked', { exact:true })).toBeVisible()
  expect(calls).toEqual([{ status:'tracked', expected_status:'pm_review', reason:'The original evidence supports this direction' }])
  await navigate(page, 'Reports')
  await expect(page.getByText('The original evidence supports this direction', { exact:true })).toBeVisible()
})

test('a refused review is visible and leaves the persisted status unchanged', async ({ page }) => {
  const data = emptySnapshot(); data.requirements = [storedRequirement()]
  await mockWorkspace(page, { snapshot:() => data })
  await page.route('**/api/requirements/*/status', r => json(r, { detail:'the requirement changed; refresh it before reviewing' }, 409))
  await page.goto('/#requirements')
  await page.getByRole('button', { name:'Stored climate requirement', exact:true }).click()
  await page.getByLabel('Review reason').fill('Reason for this review')
  await page.getByRole('button', { name:'Move to Tracked' }).click()
  await expect(page.getByRole('alert')).toHaveText('the requirement changed; refresh it before reviewing')
  await expect(page.getByRole('dialog').getByText('R-STORED / PM review')).toBeVisible()
})

test('portfolio exports use only real filtered rows and stored citations', async ({ page }) => {
  const data = emptySnapshot(); data.requirements = [storedRequirement(), { ...storedRequirement(), id:'second', title:'Another stored requirement' }]
  await mockWorkspace(page, { snapshot:() => data })
  await page.goto('/#requirements')
  await page.getByLabel('Search requirements').fill('climate')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name:'Export portfolio' }).click()
  const download = await downloaded
  const stream = await download.createReadStream()
  let text = ''; for await (const chunk of stream!) text += chunk.toString()
  expect(text).toContain('Stored climate requirement'); expect(text).toContain('real-feedback.xlsx: sheet Feedback, row 81')
  expect(text).not.toContain('Another stored requirement'); expect(text).not.toContain('Must-have')
})

test('backend failures are visible without generating a sample workspace', async ({ page }) => {
  await mockWorkspace(page, { unavailable:true })
  await page.goto('/')
  await expect(page.getByRole('heading', { name:'Workspace unavailable' })).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('database unavailable')
  await expect(page.getByText('Predictable rapid charging')).toHaveCount(0)
  await expect(page.getByRole('button', { name:'Try again' })).toBeVisible()
})

test('the connected views pass WCAG checks and fit both viewports', async ({ page }) => {
  const data = emptySnapshot(); data.requirements = [storedRequirement()]
  await mockWorkspace(page, { snapshot:() => data })
  await page.goto('/')
  await expect(page.getByRole('heading', { name:'Build what comes next.' })).toBeVisible()
  for (const name of ['Overview','Requirements','Reports']) {
    await navigate(page, name)
    await page.addScriptTag({ path:require.resolve('axe-core/axe.min.js') })
    const violations = await page.evaluate(async () => (await (window as unknown as { axe:typeof axe }).axe.run(document, { runOnly:{ type:'tag', values:['wcag2a','wcag2aa','wcag21aa'] } })).violations.map(v => ({ id:v.id, nodes:v.nodes.map(n => n.html) })))
    expect(violations).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  }
})
