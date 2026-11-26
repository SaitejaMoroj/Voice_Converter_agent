import { Moon, Settings2, Sun } from 'lucide-react'
import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import type { AppShellContext } from '../components/AppShell'

const LANGUAGE_KEY = 'voxflow.defaultLanguage'

export default function SettingsPage() {
  const [language, setLanguage] = useState(() => localStorage.getItem(LANGUAGE_KEY) ?? 'auto')
  const { isDark, toggleTheme } = useOutletContext<AppShellContext>()

  function chooseLanguage(value: string) {
    setLanguage(value)
    localStorage.setItem(LANGUAGE_KEY, value)
  }

  return (
    <section className="page-content settings-page">
      <div className="page-heading">
        <div><div className="eyebrow">PREFERENCES <span className="eyebrow-rule" /></div><h1>Settings</h1><p>Set up VoxFlow the way you like to work.</p></div>
      </div>
      <div className="settings-layout">
        <div className="settings-nav"><span className="settings-nav-active"><Settings2 size={16} />General</span></div>
        <div className="settings-content">
          <section className="settings-section">
            <div className="settings-section-heading"><div><h2>Transcription</h2><p>Choose the language VoxFlow starts with.</p></div></div>
            <label className="settings-field" htmlFor="default-language"><span><strong>Default language</strong><small>Automatic works well for more than one language.</small></span><select id="default-language" value={language} onChange={(event) => chooseLanguage(event.target.value)}><option value="auto">Automatic</option><option value="en">English</option><option value="hi">Hindi</option><option value="te">Telugu</option><option value="th">Thai</option><option value="ta">Tamil</option><option value="kn">Kannada</option></select></label>
          </section>
          <section className="settings-section">
            <div className="settings-section-heading"><div><h2>Appearance</h2><p>Choose a comfortable workspace theme.</p></div></div>
            <div className="settings-field"><span><strong>Color theme</strong><small>{isDark ? 'Dark theme is active.' : 'Light theme is active.'}</small></span><button className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${isDark ? 'light' : 'dark'} theme`}>{isDark ? <Sun size={16} /> : <Moon size={16} />}{isDark ? 'Light' : 'Dark'}</button></div>
          </section>
          <div className="settings-footnote">Preferences are stored in this browser.</div>
        </div>
      </div>
    </section>
  )
}