import { createContext, useContext } from 'react'
import type { Page } from './data'
import type { StoredRequirement, WorkspaceConfig, WorkspaceSnapshot } from './types/api'

export type WorkspaceContextValue = {
  data: WorkspaceSnapshot; config: WorkspaceConfig; line: string; market: string
  lineLabel: (key: string) => string; marketLabel: (key: string) => string
  navigate: (page: Page) => void; notify: (message: string) => void
  refresh: () => Promise<void>; openRequirement: (requirement: StoredRequirement) => void
}
export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)
export function useWorkspace() {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('Workspace provider is missing')
  return value
}
