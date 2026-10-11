// Natural Earth 1:110m country geometry is public domain. See market-impact/README.md.
// Usage: node scripts/generate-market-map.mjs /path/to/ne_110m_admin_0_countries.geojson
import { readFileSync, writeFileSync } from 'node:fs'
import { geoNaturalEarth1, geoPath } from 'd3-geo'

const source = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const features = source.features.filter((f) => f.properties.ADM0_A3 !== 'ATA')
const projection = geoNaturalEarth1().fitExtent([[16, 16], [984, 500]], { type: 'FeatureCollection', features })
const path = geoPath(projection).digits(1)
const countries = features.map((f) => {
  const p = f.properties
  // Business regions, not legislative EU membership. Russia is grouped with RoW.
  const market = p.ADM0_A3 === 'USA' ? 'US' : p.ADM0_A3 === 'CHN' ? 'CN'
    : p.CONTINENT === 'Europe' && p.ADM0_A3 !== 'RUS' ? 'EU' : 'RoW'
  return { id: p.ADM0_A3, name: p.NAME_EN, market, path: path(f) }
})
writeFileSync(new URL('../src/features/market-impact/world-map.json', import.meta.url), JSON.stringify(countries) + '\n')
