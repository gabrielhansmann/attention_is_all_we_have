import { composite, lineNames, marketNames, tier } from '../../data'
import type { Line, Market, Requirement, Source, Weights } from '../../data'

export const weightFields = [
  { key: 'relevance', label: 'Customer relevance', help: 'Give customer needs more influence.' },
  { key: 'business', label: 'Business signal', help: 'Emphasize the business opportunity.' },
  { key: 'fit', label: 'Strategic fit', help: 'Favor alignment with the programme.' },
  { key: 'effort', label: 'Effort penalty', help: 'Subtract more for difficult delivery.' },
] as const

export const lenses: { id: string; name: string; description: string; weights: Weights }[] = [
  { id: 'customer', name: 'Customer first', description: 'Put customer needs at the center.', weights: { relevance: 70, business: 15, fit: 10, effort: 5 } },
  { id: 'growth', name: 'Growth focused', description: 'Explore a stronger business signal.', weights: { relevance: 20, business: 55, fit: 20, effort: 5 } },
  { id: 'strategy', name: 'Strategic fit', description: 'Follow the programme direction.', weights: { relevance: 20, business: 10, fit: 60, effort: 10 } },
  { id: 'delivery', name: 'Delivery first', description: 'Give delivery effort more weight.', weights: { relevance: 25, business: 15, fit: 10, effort: 50 } },
]

const keys = weightFields.map(field => field.key)
export const sameWeights = (a: Weights, b: Weights) => keys.every(key => a[key] === b[key])

/** Keep integer weights at 100%, allocating rounding residue deterministically. */
export function rebalanceWeight(weights: Weights, selected: keyof Weights, value: number): Weights {
  const next = { ...weights, [selected]: Math.round(Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0))) }
  const others = keys.filter(key => key !== selected)
  const total = others.reduce((sum, key) => sum + Math.max(0, weights[key]), 0)
  const remaining = 100 - next[selected]
  const shares = others.map(key => ({ key, share: remaining * (total > 0 ? Math.max(0, weights[key]) / total : 1 / others.length) }))
  shares.forEach(({ key, share }) => { next[key] = Math.floor(share) })
  const residue = remaining - shares.reduce((sum, { key }) => sum + next[key], 0)
  shares.sort((a, b) => (b.share - Math.floor(b.share)) - (a.share - Math.floor(a.share)))
  shares.slice(0, residue).forEach(({ key }) => { next[key] += 1 })
  return next
}

export function rankRequirements(requirements: Requirement[], weights: Weights) {
  return requirements.filter(requirement => requirement.status !== 'rejected')
    .map(requirement => ({ requirement, score: composite(requirement, weights) }))
    .sort((a, b) => b.score - a.score || a.requirement.id.localeCompare(b.requirement.id))
}

export function compareScenario(requirements: Requirement[], saved: Weights, preview: Weights, slots: number) {
  const baseline = rankRequirements(requirements, saved)
  const proposed = rankRequirements(requirements, preview)
  const savedRanks = new Map(baseline.map((row, index) => [row.requirement.id, { rank: index + 1, score: row.score }]))
  const limit = Math.max(0, Math.min(Math.floor(slots), proposed.length))
  const lensShortlists = lenses.map(lens => new Set(rankRequirements(requirements, lens.weights).slice(0, limit).map(row => row.requirement.id)))
  return proposed.map((row, index) => {
    const before = savedRanks.get(row.requirement.id)!
    const shortlisted = index < limit
    const wasShortlisted = before.rank <= limit
    return { ...row, rank: index + 1, savedRank: before.rank, savedScore: before.score, movement: before.rank - index - 1,
      shortlisted, change: shortlisted ? (wasShortlisted ? 'Stays' : 'Enters') : (wasShortlisted ? 'Leaves' : 'Outside'),
      lensCount: lensShortlists.filter(shortlist => shortlist.has(row.requirement.id)).length }
  })
}

const text = (value: string) => value.replaceAll('\\', '\\\\').replaceAll('|', '\\|').replaceAll('\n', ' ').replaceAll('\r', ' ').replaceAll('<', '&lt;').replaceAll('>', '&gt;')

export function scenarioBrief(requirements: Requirement[], sources: Source[], saved: Weights, preview: Weights, slots: number, line: Line, market: Market) {
  const rows = compareScenario(requirements, saved, preview, slots)
  const lines = [
    `# Decision Lab: ${lineNames[line]} / ${marketNames[market]}`,
    '', 'Illustrative demo data. This is a scenario preview, not a product commitment or feasibility assessment.',
    `Shortlist: top ${Math.min(slots, rows.length)} non-rejected requirements in this scope. Weights apply across the demo workspace only when saved.`,
    '', '## Weight comparison', '', '| Component | Saved | Scenario |', '| --- | ---: | ---: |',
    ...weightFields.map(field => `| ${field.label} | ${saved[field.key]}% | ${preview[field.key]}% |`),
    '', 'Score = (customer relevance × weight + business signal × weight + strategic fit × weight − effort × weight) / 10000.',
    'Confidence is displayed separately and does not alter the score. Component values are on a 0–100 scale.',
    '', '## Ranking comparison', '', '| ID | Requirement | Saved rank | Scenario rank | Saved score | Scenario score | Tier | Confidence | Shortlist | Example lenses |',
    '| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: |',
    ...rows.map(row => `| ${text(row.requirement.id)} | ${text(row.requirement.title)} | ${row.savedRank} | ${row.rank} | ${row.savedScore.toFixed(4)} | ${row.score.toFixed(4)} | ${tier(row.score)} | ${row.requirement.confidence}% | ${row.change} | ${row.lensCount}/${lenses.length} |`),
    '', 'Example-lens counts measure shortlist membership across four illustrative weight presets. They are not probabilities or evidence confidence.',
    '', '## Evidence and assumptions',
  ]
  rows.filter(row => row.shortlisted || row.change === 'Leaves').forEach(({ requirement }) => {
    lines.push('', `### ${text(requirement.id)}: ${text(requirement.title)}`, `- Acceptance: ${text(requirement.acceptance)}`, `- Assumption: ${text(requirement.assumption)}`)
    requirement.sourceIds.forEach(id => {
      const source = sources.find(item => item.id === id)
      lines.push(source ? `- Source: ${text(source.name)} (${text(source.locator)}). ${text(source.excerpt)}` : `- Source unavailable: ${text(id)}`)
    })
    if (!requirement.sourceIds.length) lines.push('- No sources attached. Evidence is needed before a commitment.')
  })
  return lines.join('\n') + '\n'
}
