import type { Market } from '@/types/api'
import countries from './world-map.json'
import { IMPACT_COLORS, type Impact } from './scenario'

/** Country paths are pointer shortcuts. The four market buttons provide the same action by keyboard. */
export function WorldMap({ impacts, onSelect }: { impacts: Record<Market, Impact>; onSelect: (market: Market) => void }) {
  return (
    <svg viewBox="0 0 1000 516" aria-hidden="true" className="block w-full" data-testid="world-map">
      {countries.map((country) => {
        const market = country.market as Market
        const state = impacts[market].state
        return <path key={country.id} d={country.path} fill={IMPACT_COLORS[state]} fillOpacity={state === 'neutral' ? 0.55 : 1}
          stroke="var(--background)" strokeWidth="0.65" strokeLinejoin="round"
          className="cursor-pointer hover:opacity-70" data-market={market} data-impact={state}
          onClick={() => onSelect(market)}><title>{`${country.name}: ${state}`}</title></path>
      })}
    </svg>
  )
}
