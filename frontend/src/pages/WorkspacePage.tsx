import { useEffect, useRef, useState } from 'react'
import {
  AudioLines,
  Check,
  CircleStop,
  Clock3,
  Copy,
  Download,
  Eraser,
  Languages,
  Mic2,
  Pause,
  Pencil,
  Play,
  Radio,
  RotateCcw,
  Save,
  Sparkles,
  Waves,
} from 'lucide-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useOutletContext } from 'react-router-dom'
import TranscriptSegments from '../components/TranscriptSegments'
import type { AppShellContext } from '../components/AppShell'
import { transcriptApi } from '../services/api'
import { LiveTranscription, type StreamEvent } from '../services/transcriptionSocket'
import type { Transcript, TranscriptSegment } from '../types/transcript'
import { formatDuration as formatDurationValue } from '../lib/formatters'

const languageOptions = [
  { value: 'auto', label: 'Automatic' },
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'te', label: 'Telugu' },
  { value: 'th', label: 'Thai' },
  { value: 'ta', label: 'Tamil' },
  { value: 'kn', label: 'Kannada' },
]

function formatDuration(seconds: number): string {
  return formatDurationValue(seconds)
}

function exportText(title: string, text: string, language: string, duration: number): void {
  const blob = new Blob([`${title}\nLanguage: ${language.toUpperCase()}\nDuration: ${formatDuration(duration)}\n\n${text}`], {
    type: 'text/plain;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${title.trim().replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '') || 'transcript'}.txt`
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function WorkspacePage() {
  const { setWorkspacePhase } = useOutletContext<AppShellContext>()
  const [phase, setPhase] = useState('idle')
  const [text, setText] = useState('')
  const [partial, setPartial] = useState('')
  const [error, setError] = useState('')
  const [completed, setCompleted] = useState<Transcript | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [detectedLanguage, setDetectedLanguage] = useState('')
  const [processingTime, setProcessingTime] = useState(0)
  const [segments, setSegments] = useState<TranscriptSegment[]>([])
  const [waveform, setWaveform] = useState<number[]>(Array.from({ length: 36 }, () => 0))
  const [audioUrl, setAudioUrl] = useState('')
  const [language, setLanguage] = useState(() => localStorage.getItem('voxflow.defaultLanguage') ?? 'auto')
  const [autoSave, setAutoSave] = useState(() => localStorage.getItem('voxflow.autoSave') !== 'false')
  const [title, setTitle] = useState('Untitled session')
  const [editing, setEditing] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [notice, setNotice] = useState('')
  const [actionError, setActionError] = useState('')
  const [autosaveState, setAutosaveState] = useState('idle')
  const [savedAt, setSavedAt] = useState('')
  const [transcriptTab, setTranscriptTab] = useState<'live' | 'preview' | 'segments'>('live')
  const [client] = useState(() => new LiveTranscription())
  const stopRequested = useRef(false)
  const queryClient = useQueryClient()
  const apiHealth = useQuery({ queryKey: ['api', 'health'], queryFn: transcriptApi.health, retry: false })
  const history = useQuery({ queryKey: ['transcripts', 'recent'], queryFn: () => transcriptApi.list(4) })
  const active = ['connecting', 'loading_model', 'recording', 'processing', 'paused', 'saving'].includes(phase)
  const capturing = phase === 'recording' || phase === 'processing'
  const visibleTranscript = [text, partial].filter(Boolean).join(' ').trim()
  const wordCount = visibleTranscript ? visibleTranscript.split(/\s+/).length : 0
  const detectedLanguages = [...new Set(segments.map((segment) => segment.detected_language).filter((value): value is string => Boolean(value)))]
  const languageSummary = detectedLanguages.length
    ? detectedLanguages.map((value) => value.toUpperCase()).join(' + ')
    : detectedLanguage ? detectedLanguage.toUpperCase() : 'Awaiting speech'

  useEffect(() => {
    setWorkspacePhase(error ? 'error' : phase)
  }, [error, phase, setWorkspacePhase])

  useEffect(() => () => setWorkspacePhase('idle'), [setWorkspacePhase])

  useEffect(() => {
    if (!active || phase === 'paused') return
    const timer = window.setInterval(() => setElapsed(client.elapsedSeconds), 250)
    return () => window.clearInterval(timer)
  }, [active, client, phase])

  useEffect(() => () => client.dispose(), [client])

  async function begin() {
    stopRequested.current = false
    setError('')
    setActionError('')
    setCompleted(null)
    setText('')
    setPartial('')
    setSegments([])
    setElapsed(0)
    setProcessingTime(0)
    setDetectedLanguage('')
    setWaveform(Array.from({ length: 36 }, () => 0))
    setEditing(false)
    setDirty(false)
    setNotice('')
    setAutosaveState('saving')
    setSavedAt('')
    setAudioUrl('')
    client.clearRecording()
    setTranscriptTab('live')
    setPhase('connecting')
    try {
      await client.start(language, title, handleStreamEvent, setWaveform, autoSave)
      setPhase('recording')
    } catch (reason) {
      setPhase('error')
      setAutosaveState('idle')
      setError(reason instanceof Error ? reason.message : 'Could not start microphone.')
    }
  }

  function handleStreamEvent(event: StreamEvent) {
    if (event.type === 'session_started') {
      setPhase('loading_model')
      setAutosaveState('saved')
      if (event.saved_at) setSavedAt(event.saved_at)
    }
    if (event.type === 'status') {
      if (stopRequested.current && event.status !== 'saving') {
        if (event.save_state) setAutosaveState(event.save_state)
        if (event.saved_at) setSavedAt(event.saved_at)
        return
      }
      setPhase(event.status)
      if (event.save_state) setAutosaveState(event.save_state)
      if (event.saved_at) setSavedAt(event.saved_at)
    }
    if (event.type === 'partial_transcript') {
      setPartial(event.text)
      setDetectedLanguage(event.detected_language)
    }
    if (event.type === 'transcription_update') {
      setText(event.finalized_text)
      setPartial(event.partial_text)
      setDetectedLanguage(event.detected_language)
      setProcessingTime(event.processing_time)
      setSegments(event.segments)
    }
    if (event.type === 'final_transcript') {
      setText(event.transcript_text)
      setPartial('')
      setDetectedLanguage(event.detected_language)
      setProcessingTime(event.processing_time)
      setSegments(event.segments)
    }
    if (event.type === 'recording_ready') setAudioUrl(event.audio_url)
    if (event.type === 'session_completed') {
      stopRequested.current = false
      setCompleted(event.transcript)
      setTitle(event.transcript.title)
      setText(event.transcript.content)
      setPartial('')
      setSegments(event.transcript.segments ?? [])
      setPhase('completed')
      setElapsed(client.elapsedSeconds)
      setEditing(false)
      setDirty(false)
      setAutosaveState('saved')
      if (event.transcript.updated_at) setSavedAt(event.transcript.updated_at)
      void queryClient.invalidateQueries({ queryKey: ['transcripts'] })
      void client.getRecordingBlob().then(async (audio) => {
        if (!audio) return
        try {
          const saved = await transcriptApi.uploadAudio(event.transcript.id, audio)
          setCompleted((current) => current?.id === saved.id ? saved : current)
          if (saved.audio_url) setAudioUrl(saved.audio_url)
          setNotice('Transcript and original audio saved')
          void queryClient.invalidateQueries({ queryKey: ['transcripts'] })
        } catch {
          setActionError('Transcript saved, but the original audio could not be archived. You can still play it in this session.')
        }
      })
    }
    if (event.type === 'error') {
      if (event.retryable) {
        setAutosaveState('failed')
        setActionError(event.message)
      } else {
        setError(event.message)
        setPhase('error')
      }
    }
  }

  function pause() {
    client.pause()
    setPhase('paused')
  }

  function resume() {
    client.resume()
    setPhase('recording')
  }

  function finish() {
    if (stopRequested.current || !['recording', 'paused', 'processing'].includes(phase)) return
    stopRequested.current = true
    setPhase('saving')
    client.stop()
  }

  function retrySave() {
    setAutosaveState('saving')
    setActionError('')
    client.save()
  }

  function resetSession() {
    if (active) return
    client.reset()
    setPhase('idle')
    setError('')
    setActionError('')
    setCompleted(null)
    setText('')
    setPartial('')
    setSegments([])
    setElapsed(0)
    setProcessingTime(0)
    setDetectedLanguage('')
    setWaveform(Array.from({ length: 36 }, () => 0))
    setAudioUrl('')
    setAutosaveState('idle')
    setSavedAt('')
    setDirty(false)
    setEditing(false)
    setNotice('')
  }

  function saveNow() {
    if (!active) return
    setAutosaveState('saving')
    setActionError('')
    client.save()
  }

  async function copyTranscript() {
    try {
      await navigator.clipboard.writeText(visibleTranscript)
      setNotice('Transcript copied')
      setActionError('')
    } catch {
      setActionError('Clipboard access is unavailable in this browser.')
    }
  }

  function clearTranscript() {
    setText('')
    setPartial('')
    setSegments([])
    setDirty(Boolean(completed))
    setEditing(Boolean(completed))
    setNotice(completed ? 'Cleared locally. Save changes to update the saved transcript.' : 'Transcript cleared.')
    setActionError('')
  }

  async function saveTranscript() {
    if (!completed) return
    setPhase('saving')
    setActionError('')
    try {
      const saved = await transcriptApi.update(completed.id, { title, transcript_text: text })
      setCompleted(saved)
      setText(saved.content)
      setDirty(false)
      setEditing(false)
      setPhase('completed')
      setNotice('Changes saved to history')
      void queryClient.invalidateQueries({ queryKey: ['transcripts'] })
    } catch (reason) {
      setPhase('completed')
      setActionError(reason instanceof Error ? reason.message : 'Could not save transcript changes.')
    }
  }

  function updateAutoSave(enabled: boolean) {
    setAutoSave(enabled)
    localStorage.setItem('voxflow.autoSave', String(enabled))
  }

  const phaseLabel: Record<string, string> = {
    idle: 'Ready to record',
    connecting: 'Connecting to the service',
    loading_model: 'Preparing transcription',
    recording: 'Recording live',
    processing: 'Processing audio',
    paused: 'Recording paused',
    saving: 'Saving transcript',
    completed: 'Recording completed',
    error: 'Recording error',
  }

  const transcriptContent = transcriptTab === 'segments'
    ? <TranscriptSegments segments={segments} />
    : transcriptTab === 'preview'
      ? <div className="transcript-text-area">{text || <div className="transcript-placeholder"><strong>No finalized transcript yet</strong><span>Finalized speech appears here as windows are processed.</span></div>}</div>
      : <div className="transcript-text-area" aria-live="polite">{text || partial
        ? <>{text && <span>{text}</span>}{partial && <span className="partial-transcript">{text ? ' ' : ''}{partial}</span>}</>
        : <div className="transcript-placeholder"><Sparkles size={20} /><strong>{phaseLabel[phase] ?? phaseLabel.idle}</strong><span>Start speaking to build your transcript.</span></div>}
      </div>

  return (
    <section className="dashboard-content workspace-page">
      <section className="welcome-banner">
        <span className="welcome-banner-icon"><Mic2 size={22} /></span>
        <div className="welcome-copy">
          <h2>Welcome to VoxFlow</h2>
          <p>Speak naturally in English, Hindi, or a mix. Other model-supported languages are available; results can vary.</p>
        </div>
      </section>

      <div className="workspace-layout">
        <section className="dashboard-panel recorder-panel" aria-label="Recording controls">
          <div className="panel-topline">
            <span className={`recording-indicator ${phase === 'recording' ? 'is-recording' : phase === 'paused' ? 'is-paused' : ['processing', 'loading_model', 'connecting', 'saving'].includes(phase) ? 'is-processing' : ''}`}>
              <span className={`status-light ${phase === 'recording' ? 'recording' : phase === 'paused' ? '' : ['processing', 'loading_model', 'connecting', 'saving'].includes(phase) ? 'processing' : apiHealth.isSuccess ? 'ready' : 'error'}`} />
              {phaseLabel[phase] ?? phase}
            </span>
            <span className="language-chip" title={languageOptions.find((option) => option.value === language)?.label}><Languages size={13} />{language === 'auto' ? 'Automatic' : languageOptions.find((option) => option.value === language)?.label}</span>
          </div>

          <div className={`recorder-visual ${phase === 'paused' ? 'waveform-paused' : phase === 'idle' || phase === 'completed' || phase === 'error' ? 'waveform-idle' : ''}`} role="img" aria-label={phase === 'recording' ? 'Live microphone waveform' : 'Microphone waveform idle'}>
            <div className="waveform-bars" aria-hidden="true">
              {waveform.map((level, index) => <span className="waveform-bar" key={index} style={{ height: `${Math.max(4, level * 62)}px` }} />)}
            </div>
            <span className="mic-orbit" style={{ '--audio-level': Math.max(...waveform) } as React.CSSProperties} />
            <span className={`mic-core ${phase === 'recording' ? 'is-recording' : ''}`}><Mic2 size={31} /></span>
          </div>

          <p className="recording-time">{formatDuration(elapsed)}</p>
          <p className="recording-caption">{phaseLabel[phase] ?? phaseLabel.idle}</p>

          <div className="recorder-controls">
            {(phase === 'idle' || phase === 'completed' || phase === 'error') && (
              <span className="recorder-control-wrap">
                <button className="recorder-control primary" onClick={() => void begin()} aria-label={phase === 'error' ? 'Retry recording' : 'Start recording'} title={phase === 'error' ? 'Retry recording' : 'Start recording'}><Mic2 size={17} /></button>
                <span>{phase === 'error' ? 'Retry' : 'Start'}</span>
              </span>
            )}
            {phase === 'recording' && <>
              <span className="recorder-control-wrap"><button className="recorder-control" onClick={pause} aria-label="Pause recording" title="Pause"><Pause size={16} /></button><span>Pause</span></span>
              <span className="recorder-control-wrap"><button className="recorder-control stop" onClick={finish} aria-label="Stop recording" title="Stop"><CircleStop size={17} /></button><span>Stop</span></span>
            </>}
            {phase === 'paused' && <>
              <span className="recorder-control-wrap"><button className="recorder-control primary" onClick={resume} aria-label="Resume recording" title="Resume"><Play size={16} /></button><span>Resume</span></span>
              <span className="recorder-control-wrap"><button className="recorder-control stop" onClick={finish} aria-label="Stop recording" title="Stop"><CircleStop size={17} /></button><span>Stop</span></span>
            </>}
            {phase === 'processing' && <>
              <span className="recorder-control-wrap"><button className="recorder-control" disabled aria-label="Processing audio"><Waves size={16} /></button><span>Processing</span></span>
              <span className="recorder-control-wrap"><button className="recorder-control stop" onClick={finish} aria-label="Stop recording" title="Stop after this audio window"><CircleStop size={17} /></button><span>Stop</span></span>
            </>}
            {['connecting', 'loading_model', 'saving'].includes(phase) && <span className="recorder-control-wrap"><button className="recorder-control" disabled aria-label={phaseLabel[phase]}><Waves size={16} /></button><span>{phase === 'saving' ? 'Saving' : 'Working'}</span></span>}
            <span className="recorder-control-wrap"><button className="recorder-control" onClick={resetSession} disabled={active} aria-label="Reset workspace" title="Reset"><RotateCcw size={16} /></button><span>Reset</span></span>
          </div>

          <div className="recorder-footer"><span>{apiHealth.isSuccess ? 'Microphone ready' : 'Waiting for service'}</span><span>{phase === 'paused' ? 'Audio capture paused' : phase === 'recording' ? 'Live audio capture' : 'Speech recognition ready'}</span></div>
        </section>

        <section className="dashboard-panel transcription-panel" aria-label="Live transcript">
          <div className="panel-topline transcript-panel-header">
            <div><h2 className="panel-title">Live Transcript</h2><p className="panel-subtitle">Text appears while you speak</p></div>
            {capturing && <span className="stream-live"><span className="status-light ready" />Live</span>}
          </div>
          <div className="transcript-view-tabs" role="tablist" aria-label="Transcript views">
            <button role="tab" aria-selected={transcriptTab === 'live'} className={`transcript-view-tab ${transcriptTab === 'live' ? 'active' : ''}`} onClick={() => setTranscriptTab('live')}><Radio size={13} />Live</button>
            <button role="tab" aria-selected={transcriptTab === 'preview'} className={`transcript-view-tab ${transcriptTab === 'preview' ? 'active' : ''}`} onClick={() => setTranscriptTab('preview')}><AudioLines size={13} />Transcript Preview</button>
            <button role="tab" aria-selected={transcriptTab === 'segments'} className={`transcript-view-tab ${transcriptTab === 'segments' ? 'active' : ''}`} onClick={() => setTranscriptTab('segments')}><Waves size={13} />Segments</button>
            <span className="transcript-tools-spacer" />
            <button className="icon-button" onClick={() => void copyTranscript()} disabled={!visibleTranscript} title="Copy transcript" aria-label="Copy transcript"><Copy size={14} /></button>
            <button className="icon-button" onClick={() => exportText(title, visibleTranscript, language, elapsed)} disabled={!visibleTranscript} title="Download transcript" aria-label="Download transcript"><Download size={14} /></button>
            <button className="icon-button" onClick={clearTranscript} disabled={!visibleTranscript || active} title="Clear transcript" aria-label="Clear transcript"><Eraser size={14} /></button>
          </div>
          {editing
            ? <textarea className="transcript-edit-area" aria-label="Edit transcript" value={text} onChange={(event) => { setText(event.target.value); setDirty(true) }} />
            : transcriptContent}
          <div className="transcript-metrics">
            <span className="metric-chip detected"><Languages size={12} />Language: {languageSummary}</span>
            <span className="metric-chip"><Clock3 size={12} />Duration: {formatDuration(elapsed)}</span>
            <span className="metric-chip"><AudioLines size={12} />Words: {wordCount}</span>
            {processingTime > 0 && <span className="metric-chip">{processingTime.toFixed(1)}s processing</span>}
            {savedAt && <span className="metric-chip">Saved {new Date(savedAt).toLocaleTimeString()}</span>}
          </div>
          {audioUrl && phase === 'completed' && <audio className="transcript-audio" controls src={audioUrl} aria-label="Play local recording" />}
          {notice && <p className="workspace-notice" role="status">{notice}</p>}
          {error && <p className="workspace-error" role="alert">{error}</p>}
          {actionError && <p className="workspace-error" role="alert">{actionError}</p>}
          {completed && !editing && <div className="transcript-footer"><span><Check size={13} />Saved in history</span><button className="recent-sessions-heading-link" onClick={() => { setEditing(true); setNotice('') }}><Pencil size={13} />Edit transcript</button></div>}
          {editing && <div className="transcript-footer"><button className="recent-sessions-heading-link" onClick={() => { setEditing(false); setText(completed?.content ?? text); setDirty(false) }}>Cancel edit</button><button className="recent-sessions-heading-link" onClick={() => void saveTranscript()} disabled={!dirty || phase === 'saving'}><Save size={13} />Save changes</button></div>}
        </section>

        <aside className="dashboard-panel session-panel" aria-label="Session details">
          <div className="panel-heading"><div><h3>Session Details</h3><p>Configure this recording</p></div><Sparkles size={16} color="var(--accent-purple)" /></div>
          <div className="session-form">
            <label className="session-field">Session name<input value={title} onChange={(event) => { setTitle(event.target.value); if (completed) setDirty(true) }} maxLength={200} disabled={active} /></label>
            <label className="session-field">Language<select value={language} onChange={(event) => { setLanguage(event.target.value); localStorage.setItem('voxflow.defaultLanguage', event.target.value) }} disabled={active}>{languageOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
            <div className="session-field">Speech recognition<span className="model-readout"><AudioLines size={14} />Automatic language support</span></div>
          </div>
          <div className="autosave-setting"><span><strong>Auto-save</strong><small>{autoSave ? 'Checkpoints saved during recording' : 'Only saved when you finish'}</small></span><button className="toggle-switch" role="switch" aria-checked={autoSave} aria-label="Toggle auto-save" onClick={() => updateAutoSave(!autoSave)} disabled={active}><span /></button></div>
          <button className="session-save-button" onClick={() => active ? autosaveState === 'failed' ? retrySave() : saveNow() : completed && dirty ? void saveTranscript() : phase === 'idle' || phase === 'error' ? void begin() : undefined} disabled={(phase === 'saving' && autosaveState !== 'failed') || (phase === 'completed' && !dirty)}>
            <Save size={15} />{active ? autosaveState === 'failed' ? 'Retry save' : phase === 'saving' || autosaveState === 'saving' ? 'Saving…' : 'Save checkpoint' : completed ? dirty ? 'Save transcript' : 'Saved to history' : phase === 'error' ? 'Start again' : 'Start transcription'}
          </button>
        </aside>
      </div>

      <section className="dashboard-panel recent-sessions-panel">
        <div className="recent-sessions-heading"><div><h2>Recent Sessions</h2><p>Your saved transcription history</p></div><Link to="/history">View history <span>→</span></Link></div>
        <div className="recent-session-list">
          {history.data?.items.map((item) => <Link className="recent-session-row" key={item.id} to={`/transcripts/${item.id}`}>
            <span><span className="recent-session-title">{item.title}</span><small className="recent-session-preview">{item.content.slice(0, 100) || 'No speech detected'}</small></span>
            <span className="recent-language-tag">{item.language.toUpperCase()}</span>
            <span>{formatDuration(item.duration_seconds)}</span>
            <span>{new Date(item.created_at).toLocaleDateString()}</span>
          </Link>)}
          {history.isLoading && <div className="recent-empty">Loading your recent sessions…</div>}
          {history.isError && <div className="recent-empty" role="alert">Could not load recent sessions. Check the API connection.</div>}
          {history.data?.items.length === 0 && <div className="recent-empty">Your saved sessions will appear here.</div>}
        </div>
      </section>
    </section>
  )
}