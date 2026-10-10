import { BrowserRouter, Route, Routes } from 'react-router'
import { AppShell } from '@/components/layout/AppShell'
import { ChatPage } from '@/features/chat/ChatPage'
import { EvidencePage } from '@/features/evidence/EvidencePage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<ChatPage />} />
          <Route path="evidence" element={<EvidencePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
