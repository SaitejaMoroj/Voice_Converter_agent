import { useState } from 'react'
import { AudioLines, CalendarDays, Clock3, Copy, Download, Ellipsis, Eye, FileText, Languages, Pencil, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import HistoryAudioPlayer from './HistoryAudioPlayer'
import { formatDate, formatDuration } from '../lib/formatters'
import type { Transcript, TranscriptionStatistics } from '../types/transcript'

interface StatisticsCardsProps {
  statistics?: TranscriptionStatistics
  loading: boolean
}

export function StatisticsCards({ statistics, loading }: StatisticsCardsProps) {
  const cards = [
    { label: 'Total Sessions', value: statistics?.total_sessions, detail: 'Saved transcripts', icon: FileText, tone: 'purple' },
    { label: 'Total Duration', value: statistics ? formatDuration(statistics.total_duration_seconds) : undefined, detail: 'Archived recording time', icon: Clock3, tone: 'violet' },
    { label: 'Languages', value: statistics?.unique_languages, detail: 'Detected in saved sessions', icon: Languages, tone: 'blue' },
    { label: 'This Month', value: statistics?.sessions_this_month, detail: 'Sessions created', icon: CalendarDays, tone: 'green' },
  ]

  return (
    <section className="history-statistics" aria-label="Transcription library statistics">
      {cards.map((card) => <article className={`history-stat-card tone-${card.tone}`} key={card.label}>
        <span className="history-stat-icon" aria-hidden="true"><card.icon size={18} /></span>
        <span className="history-stat-copy"><small>{card.label}</small><strong>{loading ? '—' : card.value ?? '—'}</strong><em>{card.detail}</em></span>
      </article>)}
    </section>
  )
}

export interface SessionRowProps {
  record: Transcript
  selected: boolean
  activeAudioId: string | null
  onSelect: (id: string, selected: boolean) => void
  onActivateAudio: (id: string) => void
  onDeactivateAudio: (id: string) => void
  onEdit: (record: Transcript) => void
  onDelete: (record: Transcript) => void
  onCopy: (record: Transcript) => void
  onDownloadTranscript: (record: Transcript) => void
}

export function SessionRow({
  record,
  selected,
  activeAudioId,
  onSelect,
  onActivateAudio,
  onDeactivateAudio,
  onEdit,
  onDelete,
  onCopy,
  onDownloadTranscript,
}: SessionRowProps) {
  const [menuOpen, setMenuOpen] = useState(false)
  const language = record.language && record.language !== 'auto' ? record.language.toUpperCase() : '—'
  const preview = record.content.trim().replace(/\s+/g, ' ')

  return (
    <article className={`history-session-row ${selected ? 'is-selected' : ''}`}>
      <label className="history-select-cell">
        <input type="checkbox" checked={selected} onChange={(event) => onSelect(record.id, event.target.checked)} aria-label={`Select ${record.title}`} />
      </label>
      <div className="history-session-info">
        <span className="history-session-icon"><AudioLines size={17} /></span>
        <span className="history-session-copy">
          <Link to={`/transcripts/${record.id}`} className="history-session-title">{record.title}</Link>
          <span className="history-session-preview" title={preview}>{preview || 'No speech detected'}</span>
        </span>
      </div>
      <span className={`history-language-tag lang-${language.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>{language}</span>
      <div className="history-audio-cell">
        <HistoryAudioPlayer
          audioUrl={record.audio_available ? record.audio_url : null}
          title={record.title}
          durationSeconds={record.duration_seconds}
          active={activeAudioId === record.id}
          onActivate={() => onActivateAudio(record.id)}
          onDeactivate={() => onDeactivateAudio(record.id)}
        />
      </div>
      <span className="history-duration">{formatDuration(record.duration_seconds)}</span>
      <time className="history-created" dateTime={record.created_at}>{formatDate(record.created_at, true)}</time>
      <div className="history-row-actions">
        <Link to={`/transcripts/${record.id}`} className="history-action-button" title="View transcript" aria-label={`View ${record.title}`}><Eye size={14} /></Link>
        <button className="history-action-button" onClick={() => onEdit(record)} title="Edit transcript" aria-label={`Edit ${record.title}`}><Pencil size={14} /></button>
        <button className="history-action-button" onClick={() => onDownloadTranscript(record)} title="Download transcript" aria-label={`Download transcript for ${record.title}`}><Download size={14} /></button>
        {record.audio_available && <a className="history-action-button" href={record.audio_url ? `${record.audio_url}?download=true` : undefined} title="Download original audio" aria-label={`Download audio for ${record.title}`} download><AudioLines size={14} /></a>}
        <button className="history-action-button delete" onClick={() => onDelete(record)} title="Delete session" aria-label={`Delete ${record.title}`}><Trash2 size={14} /></button>
        <details className="history-more-actions" open={menuOpen} onToggle={(event) => setMenuOpen(event.currentTarget.open)}>
          <summary className="history-action-button" aria-label={`More actions for ${record.title}`} title="More actions"><Ellipsis size={15} /></summary>
          <div className="history-more-menu">
            <button onClick={() => { onCopy(record); setMenuOpen(false) }}><Copy size={13} />Copy transcript</button>
            <Link to={`/transcripts/${record.id}`}><Eye size={13} />Open details</Link>
          </div>
        </details>
      </div>
      <div className="history-mobile-meta"><span>{formatDuration(record.duration_seconds)}</span><span>{formatDate(record.created_at)}</span></div>
    </article>
  )
}

export function HistorySkeleton() {
  return <div className="history-skeleton-list" aria-label="Loading sessions">{Array.from({ length: 6 }, (_, index) => <div className="history-skeleton-row" key={index}><i /><span><b /><b /></span><i /><i /><i /></div>)}</div>
}

interface HistoryEmptyStateProps {
  filtered: boolean
  onClear: () => void
}

export function HistoryEmptyState({ filtered, onClear }: HistoryEmptyStateProps) {
  return (
    <div className="history-empty-state">
      <span className="history-empty-icon"><AudioLines size={24} /></span>
      <h2>{filtered ? 'No matching sessions found' : 'Your library is empty'}</h2>
      <p>{filtered ? 'Try adjusting your search or filters.' : 'Start your first recording and your sessions will appear here.'}</p>
      {filtered ? <button className="history-link-button" onClick={onClear}>Clear search and filters</button> : <Link className="history-primary-link" to="/">New transcription</Link>}
    </div>
  )
}
