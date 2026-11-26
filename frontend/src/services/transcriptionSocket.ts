import type { Transcript } from '../types/transcript'

export interface StreamSegment {
  start: number
  end: number
  text: string
  average_log_probability?: number | null
  no_speech_probability?: number | null
  detected_language?: string | null
}

export type StreamEvent =
  | { type: 'session_started'; session_id: string; transcription_id?: string; status: string; saved_at?: string }
  | { type: 'partial_transcript'; text: string; detected_language: string; segments: StreamSegment[] }
  | { type: 'transcription_update'; transcript_text: string; finalized_text: string; partial_text: string; detected_language: string; segments: StreamSegment[]; processing_time: number; status: string }
  | { type: 'final_transcript'; transcript_text: string; detected_language: string; segments: StreamSegment[]; processing_time: number; status: string }
  | { type: 'status'; status: string; session_id?: string; heartbeat?: string; save_state?: string; saved_at?: string }
  | { type: 'session_completed'; session_id: string; status: string; transcript: Transcript }
  | { type: 'recording_ready'; audio_url: string; audio_blob: Blob }
  | { type: 'error'; message: string; retryable?: boolean }

const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname)
const PRODUCTION_API_URL = 'https://voice-converter-agent.onrender.com/api/v1'
const API_URL = import.meta.env.VITE_API_URL?.trim()
const deriveSocketUrl = (apiUrl: string): string => {
  const parsed = new URL(apiUrl, window.location.origin)
  parsed.protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
  parsed.pathname = '/ws/transcription'
  parsed.search = ''
  parsed.hash = ''
  return parsed.toString()
}
const SOCKET_URL = import.meta.env.VITE_WS_URL
  ?? (API_URL
    ? deriveSocketUrl(API_URL)
    : isLocalHost
      ? 'ws://127.0.0.1:8000/ws/transcription'
      : deriveSocketUrl(PRODUCTION_API_URL))
const TARGET_SAMPLE_RATE = 16_000
const MAX_BUFFERED_BYTES = 512 * 1024
const START_TIMEOUT_MS = 90_000

export class LiveTranscription {
  private socket?: WebSocket
  private stream?: MediaStream
  private audioContext?: AudioContext
  private processor?: ScriptProcessorNode
  private source?: MediaStreamAudioSourceNode
  private mediaRecorder?: MediaRecorder
  private recordedChunks: BlobPart[] = []
  private recordingUrl?: string
  private recordingBlobPromise: Promise<Blob | null> = Promise.resolve(null)
  private resolveRecordingBlob?: (blob: Blob | null) => void
  private onEvent?: (event: StreamEvent) => void
  private onAudioLevel?: (levels: number[]) => void
  private sequence = 0
  private activeStartedAt = 0
  private elapsedBeforeActive = 0
  private state: 'idle' | 'recording' | 'paused' | 'stopping' = 'idle'

  get elapsedSeconds(): number {
    const activeElapsed = this.state === 'recording' ? (Date.now() - this.activeStartedAt) / 1000 : 0
    return Math.floor(this.elapsedBeforeActive + activeElapsed)
  }

  async start(
    language: string,
    title: string,
    onEvent: (event: StreamEvent) => void,
    onAudioLevel?: (levels: number[]) => void,
    autoSave = true,
  ): Promise<void> {
    this.sequence = 0
    this.elapsedBeforeActive = 0
    this.state = 'idle'
    this.onEvent = onEvent
    this.onAudioLevel = onAudioLevel
    this.clearRecording()
    this.recordedChunks = []
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
      this.startLocalRecorder()
    } catch (error) {
      throw new Error(this.permissionMessage(error))
    }

    this.stream.getAudioTracks().forEach((track) => {
      track.addEventListener('ended', () => {
        if (this.state === 'recording' || this.state === 'paused') {
          this.emit({ type: 'error', message: 'The microphone was disconnected.' })
          this.stop()
        }
      })
    })

    try {
      this.socket = new WebSocket(SOCKET_URL)
      this.socket.binaryType = 'arraybuffer'
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('The transcription service did not become ready in time.')), START_TIMEOUT_MS)
        const finish = (error?: Error) => {
          window.clearTimeout(timeout)
          if (error) reject(error)
          else resolve()
        }
        this.socket!.onopen = () => {
          this.socket!.send(JSON.stringify({
            type: 'start',
            title,
            language,
            auto_save: autoSave,
            sample_rate: TARGET_SAMPLE_RATE,
            format: 'pcm_s16le',
            channels: 1,
          }))
        }
        this.socket!.onerror = () => finish(new Error(`Could not connect to the transcription service at ${SOCKET_URL}.`))
        this.socket!.onclose = (event) => {
          this.releaseAudio()
          if (this.state !== 'stopping' && this.state !== 'idle') {
            this.state = 'idle'
            this.emit({ type: 'error', message: 'The transcription connection was closed.' })
          }
          finish(new Error(`The transcription connection closed before it was ready (code ${event.code}${event.reason ? `: ${event.reason}` : ''}).`))
        }
        this.socket!.onmessage = (message) => {
          let event: StreamEvent
          try {
            event = JSON.parse(message.data as string) as StreamEvent
          } catch {
            finish(new Error('The transcription service sent an invalid response.'))
            this.emit({ type: 'error', message: 'The transcription service sent an invalid response.' })
            return
          }
          this.emit(event)
          if (event.type === 'error') finish(new Error(event.message))
          if (event.type === 'status' && event.status === 'recording' && this.state === 'idle') {
            try {
              this.connectAudio()
              this.state = 'recording'
              this.activeStartedAt = Date.now()
              finish()
            } catch (error) {
              finish(error instanceof Error ? error : new Error('Could not initialize browser audio.'))
            }
          }
        }
      })
    } catch (error) {
      this.releaseAudio()
      if (this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) this.socket.close()
      this.state = 'idle'
      throw error
    }
  }

  pause(): void {
    if (this.state !== 'recording' || this.socket?.readyState !== WebSocket.OPEN) return
    this.elapsedBeforeActive += (Date.now() - this.activeStartedAt) / 1000
    this.disconnectProcessor()
    if (this.mediaRecorder?.state === 'recording') this.mediaRecorder.pause()
    this.state = 'paused'
    this.socket.send(JSON.stringify({ type: 'pause' }))
  }

  resume(): void {
    if (this.state !== 'paused' || this.socket?.readyState !== WebSocket.OPEN) return
    this.socket.send(JSON.stringify({ type: 'resume' }))
    this.connectProcessor()
    if (this.mediaRecorder?.state === 'paused') this.mediaRecorder.resume()
    this.activeStartedAt = Date.now()
    this.state = 'recording'
  }

  stop(): void {
    if (this.state === 'idle' || this.state === 'stopping') return
    this.state = 'stopping'
    this.releaseAudio()
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'stop' }))
    else this.socket?.close()
  }

  save(): void {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({ type: 'save' }))
  }

  dispose(): void {
    this.onEvent = undefined
    this.onAudioLevel = undefined
    this.stop()
    this.socket?.close()
    this.releaseAudio()
    this.state = 'idle'
    this.clearRecording()
  }

  reset(): void {
    this.dispose()
    this.sequence = 0
    this.elapsedBeforeActive = 0
    this.onEvent = undefined
    this.onAudioLevel = undefined
  }

  clearRecording(): void {
    if (this.recordingUrl) URL.revokeObjectURL(this.recordingUrl)
    this.recordingUrl = undefined
    this.recordedChunks = []
    this.resolveRecordingBlob?.(null)
    this.resolveRecordingBlob = undefined
    this.recordingBlobPromise = Promise.resolve(null)
  }

  getRecordingBlob(): Promise<Blob | null> {
    return this.recordingBlobPromise
  }

  private connectAudio(): void {
    if (!this.stream) throw new Error('Microphone stream is unavailable.')
    this.audioContext = new AudioContext()
    this.source = this.audioContext.createMediaStreamSource(this.stream)
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1)
    this.processor.onaudioprocess = (event) => {
      if (this.state !== 'recording' || this.socket?.readyState !== WebSocket.OPEN) return
      if (this.socket.bufferedAmount > MAX_BUFFERED_BYTES) {
        this.emit({ type: 'error', message: 'The connection cannot keep up with incoming audio. The session is being stopped.' })
        this.stop()
        return
      }
      const input = event.inputBuffer.getChannelData(0)
      this.onAudioLevel?.(this.getWaveformLevels(input))
      const stride = this.audioContext!.sampleRate / TARGET_SAMPLE_RATE
      const output = new Int16Array(Math.floor(input.length / stride))
      for (let index = 0; index < output.length; index++) {
        const sample = input[Math.floor(index * stride)]
        output[index] = Math.max(-1, Math.min(1, sample)) * 0x7fff
      }
      this.socket.send(JSON.stringify({
        type: 'audio_chunk',
        sequence: this.sequence++,
        format: 'pcm_s16le',
        sample_rate: TARGET_SAMPLE_RATE,
        channels: 1,
        byte_length: output.byteLength,
      }))
      this.socket.send(output.buffer)
      event.outputBuffer.getChannelData(0).fill(0)
    }
    this.connectProcessor()
  }

  private connectProcessor(): void {
    if (!this.source || !this.processor || !this.audioContext) return
    this.source.connect(this.processor)
    this.processor.connect(this.audioContext.destination)
  }

  private disconnectProcessor(): void {
    this.source?.disconnect()
    this.processor?.disconnect()
  }

  private releaseAudio(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') this.mediaRecorder.stop()
    this.mediaRecorder = undefined
    this.disconnectProcessor()
    this.stream?.getTracks().forEach((track) => {
      track.onended = null
      track.stop()
    })
    void this.audioContext?.close()
    this.processor = undefined
    this.source = undefined
    this.stream = undefined
    this.audioContext = undefined
  }

  private startLocalRecorder(): void {
    if (!this.stream || typeof MediaRecorder === 'undefined') return
    this.recordingBlobPromise = new Promise((resolve) => { this.resolveRecordingBlob = resolve })
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : undefined
    this.mediaRecorder = mimeType
      ? new MediaRecorder(this.stream, { mimeType })
      : new MediaRecorder(this.stream)
    this.mediaRecorder.addEventListener('dataavailable', (event) => {
      if (event.data.size > 0) this.recordedChunks.push(event.data)
    })
    const recorder = this.mediaRecorder
    recorder.addEventListener('stop', () => {
      const blob = new Blob(this.recordedChunks, { type: recorder.mimeType || 'audio/webm' })
      this.recordedChunks = []
      this.resolveRecordingBlob?.(blob.size > 0 ? blob : null)
      this.resolveRecordingBlob = undefined
      if (blob.size === 0 || this.state === 'idle') return
      this.recordingUrl = URL.createObjectURL(blob)
      this.emit({ type: 'recording_ready', audio_url: this.recordingUrl, audio_blob: blob })
    }, { once: true })
    recorder.start(250)
  }

  private getWaveformLevels(input: Float32Array): number[] {
    const barCount = 36
    return Array.from({ length: barCount }, (_, barIndex) => {
      const start = Math.floor(barIndex * input.length / barCount)
      const end = Math.max(start + 1, Math.floor((barIndex + 1) * input.length / barCount))
      let sum = 0
      for (let index = start; index < end; index++) sum += input[index] * input[index]
      return Math.min(1, Math.sqrt(sum / (end - start)) * 8)
    })
  }

  private permissionMessage(error: unknown): string {
    if (error instanceof DOMException) {
      if (error.name === 'NotAllowedError' || error.name === 'SecurityError') return 'Microphone access was denied. Allow microphone access and try again.'
      if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') return 'No microphone was found.'
      if (error.name === 'NotReadableError') return 'The microphone is in use by another application.'
    }
    return error instanceof Error ? error.message : 'Could not access the microphone.'
  }

  private emit(event: StreamEvent): void {
    this.onEvent?.(event)
  }
}
