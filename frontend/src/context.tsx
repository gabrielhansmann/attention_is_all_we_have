import { createContext, useContext } from 'react'
import type { Audit, Line, Market, Metric, Page, Requirement, Source, Workspace } from './data'

export type WorkspaceContextValue = {
  workspace: Workspace; line: Line; market: Market; requirements: Requirement[]; metrics: Metric[]; audits: Audit[]
  navigate: (page: Page) => void; notify: (message: string) => void
  mutate: (title: string, detail: string, update: (state: Workspace) => Workspace, actor?: string) => void
  openSource: (source: Source) => void; openRequirement: (requirement: Requirement) => void
  openTarget: (metric: Metric) => void; openImport: () => void; openWeights: () => void
}
export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)
export function useWorkspace() {
  const value = useContext(WorkspaceContext)
  if (!value) throw new Error('Workspace provider is missing')
  return value
}
