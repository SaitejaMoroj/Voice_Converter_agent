import { useEffect, useRef, useState } from 'react'
import { Pause, Play, Volume2, VolumeX } from 'lucide-react'
import { formatDuration } from '../lib/formatters'
import './HistoryAudioPlayer.css'

interface HistoryAudioPlayerProps {
  audioUrl: string | null | undefined
  title: string
  durationSeconds: number
  active: boolean
  onActivate: () => void
  onDeactivate: () => void
}

const waveformBars = [5, 11, 7, 17, 10, 22, 13, 8, 19, 12, 24, 15, 9, 18, 12, 21, 7, 16, 11, 23, 14, 8, 19, 12, 22, 10, 17, 8]
const playbackRates = [0.75, 1, 1.25, 1.5, 2]

function formatClock(seconds: number): string {
  return formatDuration(seconds)
}

export default function HistoryAudioPlayer({
  audioUrl,
  title,
  durationSeconds,
  active,
  onActivate,
  onDeactivate,
}: HistoryAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(durationSeconds)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [volume, setVolume] = useState(0.85)
  const [error, setError] = useState('')

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    audio.playbackRate = speed
    audio.volume = volume
  }, [speed, volume])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || active || audio.paused) return
    audio.pause()
    setPlaying(false)
  }, [active])

  if (!audioUrl) return <span className="history-audio-unavailable">Audio unavailable</span>

  async function togglePlayback() {
    const audio = audioRef.current
    if (!audio) return
    setError('')
    if (!audio.paused) {
      audio.pause()
      setPlaying(false)
      onDeactivate()
      return
    }
    onActivate()
    try {
      await audio.play()
      setPlaying(true)
    } catch {
      setPlaying(false)
      onDeactivate()
      setError('Could not play this audio.')
    }
  }

  function seek(value: number) {
    const audio = audioRef.current
    if (!audio) return
    audio.currentTime = value
    setCurrentTime(value)
  }

  const total = duration > 0 ? duration : durationSeconds
  const progress = total > 0 ? Math.min(1, currentTime / total) : 0

  return (
    <div className="history-audio-player" aria-label={`Audio player for ${title}`}>
      <audio
        ref={audioRef}
        src={audioUrl}
        preload="none"
        onLoadedMetadata={(event) => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : durationSeconds)}
        onDurationChange={(event) => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : durationSeconds)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onEnded={() => { setPlaying(false); setCurrentTime(0); onDeactivate() }}
        onError={() => { setPlaying(false); setError('Audio could not be loaded.') }}
      />
      <button className={`history-audio-play ${playing ? 'is-playing' : ''}`} onClick={() => void togglePlayback()} aria-label={`${playing ? 'Pause' : 'Play'} ${title}`} title={playing ? 'Pause audio' : 'Play audio'}>
        {playing ? <Pause size={13} /> : <Play size={13} fill="currentColor" />}
      </button>
      <div className="history-audio-timeline">
        <div className="history-waveform" aria-hidden="true">
          {waveformBars.map((height, index) => <span className={index / waveformBars.length < progress ? 'passed' : ''} style={{ height }} key={index} />)}
        </div>
        <input
          className="history-audio-seek"
          type="range"
          min={0}
          max={Math.max(total, 0.1)}
          step={0.1}
          value={Math.min(currentTime, total || 0)}
          onChange={(event) => seek(Number(event.target.value))}
          aria-label={`Seek ${title}`}
        />
      </div>
      <span className="history-audio-time">{formatClock(currentTime)}/{formatClock(total)}</span>
      <details className="history-audio-options">
        <summary aria-label={`Audio settings for ${title}`} title="Playback settings">{volume === 0 ? <VolumeX size={14} /> : <Volume2 size={14} />}</summary>
        <div className="audio-options-menu">
          <label>Speed<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>{playbackRates.map((rate) => <option value={rate} key={rate}>{rate}x</option>)}</select></label>
          <label>Volume<input type="range" min={0} max={1} step={0.05} value={volume} onChange={(event) => setVolume(Number(event.target.value))} aria-label={`Volume for ${title}`} /></label>
        </div>
      </details>
      {error && <span className="history-audio-error" role="status">{error}</span>}
    </div>
  )
}
