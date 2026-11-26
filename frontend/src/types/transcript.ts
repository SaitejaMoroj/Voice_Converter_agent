export interface Transcript {
  id: string
  title: string
  content: string
  language: string
  duration_seconds: number
  created_at: string
  updated_at?: string
  status?: string
  segments?: TranscriptSegment[]
  processing_time?: number
  audio_available?: boolean
  audio_url?: string | null
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  average_log_probability?: number | null
  no_speech_probability?: number | null
  detected_language?: string | null
}

export interface TranscriptList {
  items: Transcript[]
  total: number
}

export interface TranscriptionPage {
  records: Transcript[]
  total_count: number
  page: number
  page_size: number
  total_pages: number
}

export interface TranscriptionStatistics {
  total_sessions: number
  total_duration_seconds: number
  unique_languages: number
  sessions_this_month: number
}
