import { test, expect } from '@playwright/test'
import { createWorkspace, defaultWeights } from '../src/data'
import type { Weights } from '../src/data'
import { compareScenario, lenses, rankRequirements, rebalanceWeight, scenarioBrief, weightFields } from '../src/features/decision-lab/model'

test('weight adjustment preserves the budget at every slider position, including zero-weight peers', () => {
  const inputs: Weights[] = [defaultWeights, { relevance: 100, business: 0, fit: 0, effort: 0 }, { relevance: 1, business: 1, fit: 1, effort: 97 }]
  for (const input of inputs) for (const field of weightFields) for (let position = 0; position <= 100; position++) {
    const weights = rebalanceWeight(input, field.key, position)
    expect(weights[field.key]).toBe(position)
    expect(Object.values(weights).reduce((sum, weight) => sum + weight, 0)).toBe(100)
    expect(Object.values(weights).every(weight => Number.isInteger(weight) && weight >= 0 && weight <= 100)).toBe(true)
  }
  expect(rebalanceWeight(defaultWeights, 'relevance', 50)).toEqual({ relevance: 50, business: 21, fit: 12, effort: 17 })
  expect(rebalanceWeight(inputs[1], 'relevance', 0)).toEqual({ relevance: 0, business: 34, fit: 33, effort: 33 })
})

test('the growth lens exposes a concrete shortlist trade-off and exact score changes', () => {
  const requirements = createWorkspace().requirements.filter(row => row.line === 'G60' && row.market === 'EU')
  const growth = lenses.find(lens => lens.id === 'growth')!
  const rows = compareScenario(requirements, defaultWeights, growth.weights, 3)
  expect(rows.map(row => row.requirement.id).slice(0, 3)).toEqual(['D-001', 'D-002', 'D-004'])
  expect(rows[0].savedScore).toBeCloseTo(0.7225, 8)
  expect(rows[0].score).toBeCloseTo(0.8785, 8)
  expect(rows.find(row => row.requirement.id === 'D-004')).toMatchObject({ change: 'Enters', savedRank: 4, rank: 3, movement: 1 })
  expect(rows.find(row => row.requirement.id === 'D-003')).toMatchObject({ change: 'Leaves', savedRank: 3, rank: 4, movement: -1 })
  expect(rows[0].lensCount).toBe(4)
  expect(rows.find(row => row.requirement.id === 'D-007')?.requirement.confidence).toBe(48)
})

test('ranking excludes rejected rows, preserves negative scores, and breaks ties independently of input order', () => {
  const base = createWorkspace().requirements[0]
  const requirements = [{ ...base, id: 'B', confidence: 99 }, { ...base, id: 'A', confidence: 1 }, { ...base, id: 'C', status: 'rejected' as const }]
  const rows = rankRequirements(requirements, { relevance: 0, business: 0, fit: 0, effort: 100 })
  expect(rows.map(row => row.requirement.id)).toEqual(['A', 'B'])
  expect(rows[0].score).toBe(-0.15)
  expect(compareScenario(requirements, defaultWeights, defaultWeights, 10).every(row => row.change === 'Stays')).toBe(true)
  expect(compareScenario([], defaultWeights, defaultWeights, 3)).toEqual([])
})

test('scenario briefs preserve citations, assumptions, missing-source gaps, and safe table text', () => {
  const workspace = createWorkspace()
  const requirement = { ...workspace.requirements[0], title: 'Charging | everyday\nuse <test>', sourceIds: ['catalog', 'missing'] }
  const brief = scenarioBrief([requirement], workspace.sources, defaultWeights, lenses[1].weights, 3, 'G60', 'EU')
  expect(brief).toContain('Charging \\| everyday use &lt;test&gt;')
  expect(brief).toContain('Shortlist: top 1')
  expect(brief).toContain('G60_OptionList.PDF (Page 18, equipment overview)')
  expect(brief).toContain('Source unavailable: missing')
  expect(brief).toContain(requirement.acceptance)
  expect(brief).toContain('They are not probabilities or evidence confidence.')
  expect(brief).toContain('0.7225 | 0.8785')
})
