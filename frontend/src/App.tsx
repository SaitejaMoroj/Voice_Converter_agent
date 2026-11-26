import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import AnalyticsPage from './pages/AnalyticsPage'
import HistoryPage from './pages/HistoryPage'
import SettingsPage from './pages/SettingsPage'
import TranscriptPage from './pages/TranscriptPage'
import WorkspacePage from './pages/WorkspacePage'

export default function App() {
  return <Routes><Route element={<AppShell />}><Route index element={<WorkspacePage />} /><Route path="history" element={<HistoryPage />} /><Route path="analytics" element={<AnalyticsPage />} /><Route path="settings" element={<SettingsPage />} /><Route path="transcripts/:id" element={<TranscriptPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes>
}
