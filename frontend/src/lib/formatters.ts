export type DateRangeFilter = 'all' | 'today' | '7d' | '30d' | 'year'

export function formatDuration(seconds: number | null | undefined): string {
  const totalSeconds = Math.max(0, Math.round(typeof seconds === 'number' && Number.isFinite(seconds) ? seconds : 0))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const remainder = totalSeconds % 60
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
}

export function formatDate(value: string | Date | null | undefined, includeTime = false): string {
  if (!value) return '—'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(includeTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(date)
}

function localDayStart(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

export function getDateRange(filter: DateRangeFilter): { created_after?: string; created_before?: string } {
  if (filter === 'all') return {}
  const today = localDayStart(new Date())
  let start: Date
  if (filter === 'today') start = today
  else if (filter === '7d') start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 6)
  else if (filter === '30d') start = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 29)
  else start = new Date(today.getFullYear(), 0, 1)
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1)
  return { created_after: start.toISOString(), created_before: end.toISOString() }
}
