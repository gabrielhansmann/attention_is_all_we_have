import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { assessedImpact, combineDirections, impact } from '../src/features/market-impact/scenario'
import type { MarketSignal } from '../src/types/api'

const countries = JSON.parse(readFileSync(new URL('../src/features/market-impact/world-map.json', import.meta.url), 'utf8')) as { id: string; market: string; path: string }[]

test('share arithmetic uses percentage points and missing values stay unknown', () => {
  const result = (baseline: string, delta: string, included = true) => impact({ baseline, delta, reason: '' }, included)
  expect(result('12.5', '+1.25')).toMatchObject({ delta: 1.25, resulting: 13.75, state: 'positive' })
  expect(result('', '-0.5')).toMatchObject({ delta: -0.5, resulting: null, state: 'negative' })
  expect(result('12', '')).toMatchObject({ delta: null, resulting: null, state: 'unknown' })
  expect(result('12', '0')).toMatchObject({ delta: 0, resulting: 12, state: 'neutral' })
  expect(result('12', '2', false)).toMatchObject({ delta: 0, resulting: 12, state: 'neutral' })
  expect(result('12', 'unfinished input', false)).toMatchObject({ delta: 0, resulting: 12, state: 'neutral' })
  expect(result('0.1', '0.2').resulting).toBe(0.3)
  for (const [baseline, delta] of [['101', '1'], ['0', '-1'], ['99', '2'], ['abc', '1'], ['', 'Infinity'], ['', '1,2'], ['', '1e2'], ['', '0x10']]) {
    expect(result(baseline, delta)).toMatchObject({ state: 'unknown', resulting: null })
    expect(result(baseline, delta).error).toBeTruthy()
  }
})

test('real geometry covers all four business regions and contains valid paths', () => {
  expect(countries.length).toBeGreaterThan(170)
  expect(new Set(countries.map((c) => c.id)).size).toBe(countries.length)
  expect(countries.find((c) => c.id === 'USA')?.market).toBe('US')
  expect(countries.find((c) => c.id === 'CHN')?.market).toBe('CN')
  expect(countries.find((c) => c.id === 'DEU')?.market).toBe('EU')
  expect(countries.find((c) => c.id === 'RUS')?.market).toBe('RoW')
  expect(countries.some((c) => c.id === 'ATA')).toBe(false)
  for (const country of countries) {
    expect(['US', 'EU', 'CN', 'RoW']).toContain(country.market)
    expect(country.path).toMatch(/^M/)
    expect(country.path).not.toContain('NaN')
  }
})

test('automatic signals supply direction without inventing a share change and manual scenarios override them', () => {
  const signal: MarketSignal = { market: 'US', direction: 'positive', explanation: 'Customer requests', total_feedback: 20,
    matched_total: 1, counts: { positive: 0, request: 1, negative: 0 }, reviewed: 1, evidence: [] }
  expect(assessedImpact({ baseline: '12', delta: '', reason: '' }, true, signal))
    .toMatchObject({ state: 'positive', basis: 'evidence', delta: null, resulting: null })
  expect(assessedImpact({ baseline: '12', delta: '-1', reason: '' }, true, signal))
    .toMatchObject({ state: 'negative', basis: 'scenario', resulting: 11 })
  expect(assessedImpact({ baseline: '12', delta: '', reason: '' }, false, signal))
    .toMatchObject({ state: 'neutral', basis: 'excluded', resulting: 12 })
  expect(assessedImpact({ baseline: 'invalid', delta: '', reason: '' }, true, signal))
    .toMatchObject({ state: 'unknown', basis: 'scenario' })
})


test('public and internal conflicts are preserved instead of averaged away', () => {
  expect(combineDirections('positive', 'negative')).toBe('mixed')
  expect(combineDirections('insufficient', 'positive')).toBe('positive')
  expect(combineDirections('negative', 'insufficient')).toBe('negative')
  expect(combineDirections('positive', 'mixed')).toBe('mixed')
})
