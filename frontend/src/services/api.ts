import type { Transcript, TranscriptList, TranscriptSegment, TranscriptionPage, TranscriptionStatistics } from '../types/transcript'

const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
const PRODUCTION_API_URL = 'https://voice-converter-agent-s1ru.onrender.com/api/v1'
const API_URL = import.meta.env.VITE_API_URL?.trim()
  || (isLocalHost ? 'http://127.0.0.1:8000/api/v1' : PRODUCTION_API_URL)
const API_ROOT = API_URL.replace(/\/v1\/?$/, '')

interface ApiTranscription {
  id: string
  title: string
  transcript_text: string
  detected_language: string | null
  duration_seconds: number | null
  status: string
  created_at: string
  updated_at: string
  metadata?: { segments?: TranscriptSegment[]; processing_time?: number } | null
  audio_available?: boolean
  audio_url?: string | null
}

function mapTranscription(record: ApiTranscription): Transcript {
  return {
    id: record.id,
    title: record.title,
    content: record.transcript_text,
    language: record.detected_language ?? 'auto',
    duration_seconds: record.duration_seconds ?? 0,
    created_at: record.created_at,
    updated_at: record.updated_at,
    status: record.status,
    segments: record.metadata?.segments ?? [],
    processing_time: record.metadata?.processing_time,
    audio_available: record.audio_available ?? false,
    audio_url: record.audio_url
      ? record.audio_url.startsWith('http')
        ? record.audio_url
        : new URL(record.audio_url, API_ROOT).toString()
      : null,
  }
}

async function request<T>(path: string, init?: RequestInit, baseUrl = API_URL): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const transcriptApi = {
  health: () => request<{ status: string }>('/health', undefined, `${API_ROOT}`),
  list: (limit = 50, offset = 0) => request<TranscriptList>(`/transcripts?limit=${limit}&offset=${offset}`),
  listPage: async (options: {
    page: number
    page_size: number
    search: string
    sort_by: 'created_at' | 'title' | 'duration_seconds'
    sort_order: 'asc' | 'desc'
    language?: string
    created_after?: string
    created_before?: string
  }): Promise<TranscriptionPage> => {
    const params = new URLSearchParams({
      page: String(options.page),
      page_size: String(options.page_size),
      sort_by: options.sort_by,
      sort_order: options.sort_order,
    })
    if (options.search) params.set('search', options.search)
    if (options.language) params.set('language', options.language)
    if (options.created_after) params.set('created_after', options.created_after)
    if (options.created_before) params.set('created_before', options.created_before)
    const result = await request<Omit<TranscriptionPage, 'records'> & { records: ApiTranscription[] }>(
      `/transcriptions?${params.toString()}`,
      undefined,
      API_ROOT,
    )
    return { ...result, records: result.records.map(mapTranscription) }
  },
  statistics: () => request<TranscriptionStatistics>('/transcriptions/stats', undefined, API_ROOT),
  languages: () => request<string[]>('/transcriptions/languages', undefined, API_ROOT),
  bulkRemove: (ids: string[]) => request<{ deleted_count: number }>('/transcriptions/bulk', {
    method: 'DELETE',
    body: JSON.stringify({ ids }),
  }, API_ROOT),
  uploadAudio: async (id: string, audio: Blob) => {
    const saved = await request<ApiTranscription>(`/transcriptions/${id}/audio`, {
      method: 'PUT',
      body: audio,
      headers: { 'Content-Type': audio.type || 'audio/webm' },
    }, API_ROOT)
    return mapTranscription(saved)
  },
  audioDownloadUrl: (id: string) => `${API_ROOT}/transcriptions/${id}/audio?download=true`,
  get: async (id: string) => mapTranscription(await request<ApiTranscription>(`/transcriptions/${id}`, undefined, API_ROOT)),
  update: async (id: string, data: { title: string; transcript_text: string }) => {
    const saved = await request<ApiTranscription>(`/transcriptions/${id}`, { method: 'PUT', body: JSON.stringify(data) }, API_ROOT)
    return mapTranscription(saved)
  },
  remove: (id: string) => request<void>(`/transcriptions/${id}`, { method: 'DELETE' }, API_ROOT),
}
