import type {
  AgentInfo,
  ConversationDetail,
  Conversation,
  Coverage,
  EvidenceFilters,
  FilterOptions,
  GroupBy,
  Health,
  PostResult,
  SearchResponse,
  SearchSource,
  SourceInfo,
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

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      signal,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
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

const get = <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal)

export const api = {
  health: (signal?: AbortSignal) => get<Health>('/health', signal),
  filters: (signal?: AbortSignal) => get<FilterOptions>('/evidence/filters', signal),
  search: (q: string, source: SearchSource, f: EvidenceFilters, signal?: AbortSignal) =>
    get<SearchResponse>(`/evidence/search?${query({ q, source, ...f })}`, signal),
  stats: (groupBy: GroupBy, f: EvidenceFilters, signal?: AbortSignal) =>
    get<StatsResponse>(`/evidence/stats?${query({ group_by: groupBy, ...f })}`, signal),
  sources: (signal?: AbortSignal) => get<SourceInfo[]>('/sources', signal),
  coverage: (signal?: AbortSignal) => get<Coverage>('/evidence/coverage', signal),
  agents: (signal?: AbortSignal) => get<AgentInfo[]>('/agents', signal),
  conversations: (signal?: AbortSignal) => get<Conversation[]>('/conversations', signal),
  conversation: (id: string, signal?: AbortSignal) => get<ConversationDetail>(`/conversations/${id}`, signal),
  createConversation: (requestText: string) =>
    request<ConversationDetail>('POST', '/conversations', { request: requestText }),
  postRequest: (id: string, content: string) =>
    request<PostResult>('POST', `/conversations/${id}/messages`, { content }),
  editPlan: (runId: string, agents: string[]) => request<PostResult>('PUT', `/runs/${runId}/plan`, { agents }),
}
