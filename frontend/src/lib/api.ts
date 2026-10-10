import type {
  EvidenceFilters,
  FilterOptions,
  GroupBy,
  Health,
  SearchResponse,
  SearchSource,
  StatsResponse,
} from '@/types/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v))
  return q.toString()
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, { signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'Cannot reach the backend. Is it running?')
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: (signal?: AbortSignal) => get<Health>('/health', signal),
  filters: (signal?: AbortSignal) => get<FilterOptions>('/evidence/filters', signal),
  search: (q: string, source: SearchSource, f: EvidenceFilters, signal?: AbortSignal) =>
    get<SearchResponse>(`/evidence/search?${query({ q, source, ...f })}`, signal),
  stats: (groupBy: GroupBy, f: EvidenceFilters, signal?: AbortSignal) =>
    get<StatsResponse>(`/evidence/stats?${query({ group_by: groupBy, ...f })}`, signal),
}
