import { useQuery } from '@tanstack/react-query'
import { Activity, AudioLines, Clock3, Languages } from 'lucide-react'
import { Link } from 'react-router-dom'
import { transcriptApi } from '../services/api'
import { formatDuration } from '../lib/formatters'

export default function AnalyticsPage() {
  const query = useQuery({
    queryKey: ['analytics', 'transcriptions'],
    queryFn: () => transcriptApi.listPage({
      page: 1,
      page_size: 100,
      search: '',
      sort_by: 'created_at',
      sort_order: 'desc',
    }),
  })
  const records = query.data?.records ?? []
  const languageCounts = records.reduce<Record<string, number>>((counts, record) => {
    const language = record.language.toUpperCase()
    counts[language] = (counts[language] ?? 0) + 1
    return counts
  }, {})
  const languages = Object.entries(languageCounts).sort((first, second) => second[1] - first[1])
  const totalDuration = records.reduce((sum, record) => sum + record.duration_seconds, 0)
  const durations = [...records].slice(0, 7).reverse()
  const maxDuration = Math.max(...durations.map((record) => record.duration_seconds), 1)

  return (
    <section className="dashboard-content analytics-page">
      <div className="page-intro">
        <div><span className="eyebrow">YOUR WORKSPACE</span><h2>Transcription analytics</h2><p>Activity and language breakdown from your saved sessions.</p></div>
        <span className="analytics-scope">Latest {records.length} of {query.data?.total_count ?? 0} sessions</span>
      </div>
      {query.isError && <p className="inline-error" role="alert">Analytics could not be loaded. Check the API connection and try again.</p>}
      <div className="analytics-metrics">
        <article className="metric-card"><span className="metric-icon"><AudioLines size={18} /></span><span className="metric-label">Saved sessions</span><strong>{query.isLoading ? '—' : query.data?.total_count ?? 0}</strong><small>Across your workspace</small></article>
        <article className="metric-card"><span className="metric-icon"><Clock3 size={18} /></span><span className="metric-label">Recent audio</span><strong>{formatDuration(totalDuration)}</strong><small>From the latest {records.length} sessions</small></article>
        <article className="metric-card"><span className="metric-icon"><Languages size={18} /></span><span className="metric-label">Languages detected</span><strong>{languages.length}</strong><small>{languages.slice(0, 3).map(([language]) => language).join(' · ') || 'No sessions yet'}</small></article>
        <article className="metric-card"><span className="metric-icon"><Activity size={18} /></span><span className="metric-label">Completed</span><strong>{records.filter((record) => record.status?.toLowerCase() === 'completed').length}</strong><small>In the latest {records.length} sessions</small></article>
      </div>
      <div className="analytics-grid">
        <section className="dashboard-panel activity-panel">
          <div className="panel-heading"><div><h3>Recent session duration</h3><p>Recorded minutes, newest sessions</p></div></div>
          {durations.length ? <div className="duration-chart" role="img" aria-label="Duration of recent transcription sessions">
            {durations.map((record) => <div className="duration-column" key={record.id} title={`${record.title}: ${Math.round(record.duration_seconds)} seconds`}><span style={{ height: `${Math.max(4, record.duration_seconds / maxDuration * 100)}%` }} /><small>{new Date(record.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</small></div>)}
          </div> : <div className="analytics-empty">Saved sessions will appear here.</div>}
        </section>
        <section className="dashboard-panel language-panel">
          <div className="panel-heading"><div><h3>Language breakdown</h3><p>Detected or selected session language</p></div></div>
          {languages.length ? <ul className="language-breakdown">{languages.map(([language, count]) => <li key={language}><span>{language}</span><div className="language-bar"><span style={{ width: `${count / records.length * 100}%` }} /></div><strong>{count}</strong></li>)}</ul> : <div className="analytics-empty">No language data yet.</div>}
        </section>
      </div>
      <Link to="/history" className="analytics-history-link">View transcription history <span>→</span></Link>
    </section>
  )
}