import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AudioLines, BarChart3, Clock3, Mic2, Moon, Settings2, Sun } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { transcriptApi } from '../services/api'
import './dashboard.css'

export interface AppShellContext {
  setWorkspacePhase: (phase: string) => void
  isDark: boolean
  toggleTheme: () => void
}

export default function AppShell() {
  const service = useQuery({ queryKey: ['api', 'health'], queryFn: transcriptApi.health, refetchInterval: 10_000, retry: false })
  const [workspacePhase, setWorkspacePhase] = useState('idle')
  const [isDark, setIsDark] = useState(() => localStorage.getItem('voxflow.theme') !== 'light')
  const location = useLocation()

  useEffect(() => {
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
    localStorage.setItem('voxflow.theme', isDark ? 'dark' : 'light')
  }, [isDark])

  const toggleTheme = () => setIsDark((current) => !current)
  const routeTitle = location.pathname === '/history'
    ? 'Transcription History'
    : location.pathname === '/analytics'
      ? 'Analytics'
      : location.pathname.startsWith('/settings')
        ? 'Settings'
        : location.pathname.startsWith('/transcripts/')
          ? 'Transcript Details'
          : 'Speech Workspace'
  const phaseStatus: Record<string, { label: string; tone: string }> = {
    connecting: { label: 'Connecting', tone: 'connecting' },
    loading_model: { label: 'Preparing', tone: 'processing' },
    recording: { label: 'Recording', tone: 'recording' },
    paused: { label: 'Paused', tone: 'paused' },
    processing: { label: 'Processing', tone: 'processing' },
    saving: { label: 'Saving', tone: 'processing' },
    error: { label: 'Error', tone: 'error' },
  }
  const systemStatus = !service.isSuccess
    ? service.isLoading ? { label: 'Connecting', tone: 'connecting' } : { label: 'System Offline', tone: 'error' }
    : phaseStatus[workspacePhase] ?? { label: 'System Ready', tone: 'ready' }

  return (
    <div className="app-shell dashboard-shell">
      <aside className="dashboard-sidebar">
        <NavLink to="/" className="dashboard-brand">
          <span className="dashboard-brand-mark"><AudioLines size={20} /></span>
          <span><strong>VoxFlow</strong><small>Speech Workspace</small></span>
        </NavLink>
        <div className="dashboard-nav-label">Workspace</div>
        <nav className="dashboard-nav" aria-label="Main navigation">
          <NavLink to="/" end className={({ isActive }) => `dashboard-nav-link ${isActive ? 'active' : ''}`}><Mic2 size={17} />Transcribe</NavLink>
          <NavLink to="/history" className={({ isActive }) => `dashboard-nav-link ${isActive ? 'active' : ''}`}><Clock3 size={17} />History</NavLink>
          <NavLink to="/analytics" className={({ isActive }) => `dashboard-nav-link ${isActive ? 'active' : ''}`}><BarChart3 size={17} />Analytics</NavLink>
          <NavLink to="/settings" className={({ isActive }) => `dashboard-nav-link ${isActive ? 'active' : ''}`}><Settings2 size={17} />Settings</NavLink>
        </nav>
        <div className="dashboard-sidebar-bottom">
          <div className="sidebar-connection"><span className={`status-light ${service.isSuccess ? 'ready' : service.isLoading ? 'connecting' : 'error'}`} />{service.isSuccess ? 'System connected' : service.isLoading ? 'Connecting' : 'System offline'}</div>
          <div className="sidebar-profile"><span className="profile-avatar">V</span><span><strong>My Workspace</strong><small>Local account</small></span></div>
        </div>
      </aside>
      <main className="dashboard-main">
        <header className="dashboard-header">
          <div className="dashboard-header-copy">
            <h1>{routeTitle}</h1>
            <p>Record and convert speech into text</p>
          </div>
          <div className="dashboard-header-actions">
            <div className={`system-status status-${systemStatus.tone}`} role="status"><span className="status-light" />{systemStatus.label}</div>
            <button className="icon-button theme-button" onClick={toggleTheme} title={`Switch to ${isDark ? 'light' : 'dark'} theme`} aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}>
              {isDark ? <Sun size={17} /> : <Moon size={17} />}
            </button>
            <span className="header-avatar" aria-label="My workspace">V</span>
          </div>
        </header>
        <Outlet context={{ setWorkspacePhase, isDark, toggleTheme } satisfies AppShellContext} />
      </main>
    </div>
  )
}
