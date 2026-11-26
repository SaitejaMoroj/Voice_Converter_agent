import type { TranscriptSegment } from '../types/transcript'
import './TranscriptSegments.css'

interface TranscriptSegmentsProps {
  segments?: TranscriptSegment[]
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  const remainder = (seconds % 60).toFixed(1).padStart(4, '0')
  return `${minutes}:${remainder}`
}

export default function TranscriptSegments({ segments = [] }: TranscriptSegmentsProps) {
  if (segments.length === 0) return null

  return (
    <section className="transcript-segments" aria-label="Transcript segments">
      <h2>Segments</h2>
      <ol>
        {segments.map((segment, index) => (
          <li key={`${segment.start}-${segment.end}-${index}`}>
            <time>{formatTime(segment.start)}–{formatTime(segment.end)}</time>
            <span className="segment-text">{segment.text}</span>
            {segment.detected_language && <span className="segment-language">{segment.detected_language.toUpperCase()}</span>}
            {segment.average_log_probability != null && (
              <span
                className="segment-metric"
                title="Average token log probability; this is not a calibrated confidence score."
              >
                log p {segment.average_log_probability.toFixed(2)}
              </span>
            )}
            {segment.no_speech_probability != null && (
              <span className="segment-metric" title="Model-estimated probability that this segment is non-speech audio.">
                no-speech {(segment.no_speech_probability * 100).toFixed(0)}%
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}