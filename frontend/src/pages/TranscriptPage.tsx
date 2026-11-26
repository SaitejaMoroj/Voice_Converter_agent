import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, AudioLines, Clock3, Copy, Download, Languages } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { transcriptApi } from '../services/api'
import { Button } from '../components/ui/button'
import TranscriptSegments from '../components/TranscriptSegments'
import HistoryAudioPlayer from '../components/HistoryAudioPlayer'
import { formatDate, formatDuration } from '../lib/formatters'

export default function TranscriptPage() {
  const { id = '' } = useParams()
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')
  const query = useQuery({ queryKey: ['transcript', id], queryFn: () => transcriptApi.get(id), enabled: Boolean(id) })
  const transcript = query.data

  function downloadTranscript() {
    if (!transcript) return
    const blob = new Blob([`${transcript.title}\n\n${transcript.content}`], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${transcript.title.trim().replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '') || 'transcript'}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  async function copyText() {
    if (!transcript) return
    try {
      await navigator.clipboard.writeText(transcript.content)
      setCopied(true)
      setCopyError('')
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopyError('Clipboard access is unavailable in this browser.')
    }
  }

  if (query.isLoading) return <section className="page-content"><p className="list-message">Loading transcript…</p></section>
  if (query.isError || !transcript) return <section className="page-content"><Link to="/history" className="back-link"><ArrowLeft size={16} />Back to history</Link><p className="error-message">This transcript could not be found.</p></section>

  return (
    <section className="page-content detail-page">
      <Link to="/history" className="back-link"><ArrowLeft size={16} />All transcripts</Link>
      <div className="page-heading detail-heading">
        <div>
          <div className="eyebrow">TRANSCRIPT <span className="eyebrow-rule" /></div>
          <h1>{transcript.title}</h1>
          <p>Recorded {formatDate(transcript.created_at, true)}</p>
        </div>
        <div className="detail-actions">
          <Button variant="outline" onClick={copyText} title="Copy transcript"><Copy size={16} />{copied ? 'Copied' : 'Copy text'}</Button>
          <Button variant="outline" onClick={downloadTranscript} title="Download transcript"><Download size={16} />TXT</Button>
          {transcript.audio_available && transcript.audio_url && <a className="button-outline detail-download-audio" href={`${transcript.audio_url}?download=true`} download><Download size={16} />Audio</a>}
        </div>
      </div>
      <div className="detail-meta">
        <span><Languages size={16} />{transcript.language.toUpperCase()}</span>
        <span><Clock3 size={16} />{formatDuration(transcript.duration_seconds)}</span>
        <span className="detail-status"><span className="status-dot" />{transcript.status ?? 'completed'}</span>
        <span><AudioLines size={16} />Speech recognition</span>
        <span>Updated {formatDate(transcript.updated_at ?? transcript.created_at, true)}</span>
      </div>
      {copyError && <p className="error-message" role="alert">{copyError}</p>}
      {transcript.audio_available && transcript.audio_url && <section className="detail-audio-player"><HistoryAudioPlayer audioUrl={transcript.audio_url} title={transcript.title} durationSeconds={transcript.duration_seconds} active={true} onActivate={() => undefined} onDeactivate={() => undefined} /></section>}
      <article className="detail-transcript">
        {transcript.content || <span className="muted">No speech was detected during this session.</span>}
      </article>
      <TranscriptSegments segments={transcript.segments} />
      {transcript.processing_time != null && <p className="processing-time">Model processing time: {transcript.processing_time.toFixed(1)}s</p>}
    </section>
  )
}
