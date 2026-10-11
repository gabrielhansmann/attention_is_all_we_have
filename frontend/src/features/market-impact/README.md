# Market map geometry

`world-map.json` contains preprojected Natural Earth 1:110m country paths using the Natural Earth projection.
The geometry is [public domain](https://www.naturalearthdata.com/about/terms-of-use/), from
[Natural Earth vector](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson).
It is bundled locally; the browser never calls a tile provider.

Regenerate from that GeoJSON with `node scripts/generate-market-map.mjs <downloaded-file>` from `frontend/`.
D3 is a development dependency only. Antarctica is omitted. For this schematic business-region view, Europe
excluding Russia maps to EU, China to CN, the United States to US, and every other country to RoW. This is not
an EU membership map or a country-level forecast. All countries in a group share one market assumption.
