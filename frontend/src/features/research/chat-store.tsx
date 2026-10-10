import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError } from '@/lib/api'
import type { Conversation } from '@/types/api'

interface ChatStore {
  list: Conversation[]
  listLoading: boolean
  listError: string | null
  activeId: string | null
  select: (id: string | null) => void
  refresh: () => Promise<void>
}

const Ctx = createContext<ChatStore | null>(null)
const aborted = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'

/** Conversation history and the open conversation, shared by the sidebar and the thread. */
export function ChatProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<Conversation[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [activeId, select] = useState<string | null>(null)

  const refresh = useCallback(
    () =>
      api.conversations().then((c) => { setList(c); setListError(null) })
        .catch((e) => { if (!aborted(e)) setListError(e instanceof ApiError ? e.message : 'Something went wrong.') })
        .finally(() => setListLoading(false)),
    [],
  )
  useEffect(() => { void refresh() }, [refresh])

  const value = useMemo(() => ({ list, listLoading, listError, activeId, select, refresh }), [list, listLoading, listError, activeId, refresh])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useChats(): ChatStore {
  const v = useContext(Ctx)
  if (!v) throw new Error('useChats needs ChatProvider')
  return v
}
