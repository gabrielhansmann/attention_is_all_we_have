// Live mode talks to the backend through /api. It is on in local development, and in a deployment that
// serves /api when VITE_LIVE_EVIDENCE=true. The static demo build has it off and uses the local fixtures.
export const liveEnabled = import.meta.env.DEV || import.meta.env.VITE_LIVE_EVIDENCE === 'true'

export const MARKET_LABELS: Record<string, string> = {
  EU: 'Europe',
  CN: 'China',
  US: 'USA',
  RoW: 'Rest of world',
  ALL: 'All markets',
}
export const LINE_LABELS: Record<string, string> = {
  F70: 'F70 (1 Series)',
  G60: 'G60 (5 Series)',
  G68: 'G68 (5 Series, China)',
  G70: 'G70 (7 Series)',
  ALL: 'All lines',
}
