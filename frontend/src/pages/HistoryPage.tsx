import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, FileAudio, Languages, RefreshCw, Search, Trash2 } from 'lucide-react'
import { HistoryEmptyState, HistorySkeleton, SessionRow, StatisticsCards } from '../components/HistoryComponents'
import { transcriptApi } from '../services/api'
import { formatDate, getDateRange, type DateRangeFilter } from '../lib/formatters'
import type { Transcript } from '../types/transcript'
import './HistoryPage.css'

const PAGE_SIZE = 6

type SortMode = 'newest' | 'oldest' | 'title-asc' | 'title-desc' | 'duration-asc' | 'duration-desc'
type DeleteTarget = { kind: 'single'; record: Transcript } | { kind: 'bulk' } | null

const sortOptions: Array<{ value: SortMode; label: string; sort_by: 'created_at' | 'title' | 'duration_seconds'; sort_order: 'asc' | 'desc' }> = [
  { value: 'newest', label: 'Newest first', sort_by: 'created_at', sort_order: 'desc' },
  { value: 'oldest', label: 'Oldest first', sort_by: 'created_at', sort_order: 'asc' },
  { value: 'title-asc', label: 'Title A-Z', sort_by: 'title', sort_order: 'asc' },
  { value: 'title-desc', label: 'Title Z-A', sort_by: 'title', sort_order: 'desc' },
  { value: 'duration-asc', label: 'Duration ascending', sort_by: 'duration_seconds', sort_order: 'asc' },
  { value: 'duration-desc', label: 'Duration descending', sort_by: 'duration_seconds', sort_order: 'desc' },
]

export default function HistoryPage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [language, setLanguage] = useState('')
  const [dateFilter, setDateFilter] = useState<DateRangeFilter>('all')
  const [sortMode, setSortMode] = useState<SortMode>('newest')
  const [page, setPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [activeAudioId, setActiveAudioId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null)
  const [editTarget, setEditTarget] = useState<Transcript | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftText, setDraftText] = useState('')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')
  const queryClient = useQueryClient()

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3000)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    if ((!deleteTarget && !editTarget) || busy) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDeleteTarget(null)
        setEditTarget(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [busy, deleteTarget, editTarget])

  const dateRange = getDateRange(dateFilter)
  const selectedSort = sortOptions.find((option) => option.value === sortMode) ?? sortOptions[0]
  const query = useQuery({
    queryKey: ['transcriptions', page, PAGE_SIZE, debouncedSearch, language, dateFilter, sortMode],
    queryFn: () => transcriptApi.listPage({
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch,
      sort_by: selectedSort.sort_by,
      sort_order: selectedSort.sort_order,
      language: language || undefined,
      ...dateRange,
    }),
    placeholderData: (previous) => previous,
  })
  const statistics = useQuery({ queryKey: ['transcriptions', 'statistics'], queryFn: transcriptApi.statistics })
  const languageOptions = useQuery({ queryKey: ['transcriptions', 'languages'], queryFn: transcriptApi.languages })
  const result = query.data
  const records = result?.records ?? []
  const totalCount = result?.total_count ?? 0
  const totalPages = result?.total_pages ?? 0
  const firstItem = totalCount === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastItem = Math.min(page * PAGE_SIZE, totalCount)
  const allVisibleSelected = records.length > 0 && records.every((record) => selectedIds.includes(record.id))
  const hasFilters = Boolean(search.trim() || language || dateFilter !== 'all')

  function resetPageAndSelection() {
    setPage(1)
    setSelectedIds([])
  }

  function clearFilters() {
    setSearch('')
    setDebouncedSearch('')
    setLanguage('')
    setDateFilter('all')
    setSortMode('newest')
    resetPageAndSelection()
  }

  async function refresh() {
    await Promise.all([query.refetch(), statistics.refetch(), languageOptions.refetch()])
  }

  async function copyRecord(record: Transcript) {
    try {
      await navigator.clipboard.writeText(record.content)
      setToast('Transcript copied')
    } catch {
      setToast('Clipboard access is unavailable in this browser')
    }
  }

  function downloadTranscript(record: Transcript) {
    const blob = new Blob([`${record.title}\n\n${record.content}`], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${record.title.trim().replace(/[^a-z0-9-_]+/gi, '-').replace(/^-|-$/g, '') || 'transcript'}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
    setToast('Transcript downloaded')
  }

  function startEdit(record: Transcript) {
    setEditTarget(record)
    setDraftTitle(record.title)
    setDraftText(record.content)
  }

  async function saveEdit() {
    if (!editTarget) return
    setBusy(true)
    try {
      await transcriptApi.update(editTarget.id, { title: draftTitle, transcript_text: draftText })
      const editedId = editTarget.id
      setEditTarget(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['transcriptions'] }),
        queryClient.invalidateQueries({ queryKey: ['transcript', editedId] }),
        queryClient.invalidateQueries({ queryKey: ['transcriptions', 'statistics'] }),
      ])
      setToast('Transcript changes saved')
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'Could not save transcript')
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setBusy(true)
    try {
      if (deleteTarget.kind === 'bulk') {
        const result = await transcriptApi.bulkRemove(selectedIds)
        setToast(`${result.deleted_count} session${result.deleted_count === 1 ? '' : 's'} deleted`)
        setSelectedIds([])
      } else {
        const removedId = deleteTarget.record.id
        await transcriptApi.remove(removedId)
        setToast('Session deleted')
        setSelectedIds((ids) => ids.filter((id) => id !== removedId))
        if (page > 1 && records.length === 1) setPage((current) => current - 1)
        await queryClient.invalidateQueries({ queryKey: ['transcript', removedId] })
      }
      setDeleteTarget(null)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['transcriptions'] }),
        queryClient.invalidateQueries({ queryKey: ['transcriptions', 'statistics'] }),
        queryClient.invalidateQueries({ queryKey: ['transcriptions', 'languages'] }),
      ])
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'Could not delete the selected session')
    } finally {
      setBusy(false)
    }
  }

  function toggleSelection(id: string, checked: boolean) {
    setSelectedIds((current) => checked ? [...new Set([...current, id])] : current.filter((value) => value !== id))
  }

  function toggleVisible(checked: boolean) {
    setSelectedIds((current) => checked
      ? [...new Set([...current, ...records.map((record) => record.id)])]
      : current.filter((id) => !records.some((record) => record.id === id)))
  }

  function changePage(nextPage: number) {
    setPage(nextPage)
    setSelectedIds([])
  }

  return (
    <section className="dashboard-content history-page">
      <div className="page-intro">
        <div><h2>Transcription History</h2><p>Find, revisit, and manage your saved sessions.</p></div>
        <span className="history-current-date"><CalendarDays size={13} />{formatDate(new Date())}</span>
      </div>
      <section className="history-library-banner">
        <span className="history-banner-icon"><FileAudio size={22} /></span>
        <div className="history-banner-copy"><h2>Your Transcription Library</h2><p>All your recordings, transcripts, and audio sessions in one place.</p></div>
      </section>

      {statistics.isError && <p className="history-inline-error" role="alert">Statistics are temporarily unavailable.</p>}
      <StatisticsCards statistics={statistics.data} loading={statistics.isLoading} />

      <div className="history-toolbar">
        <label className="history-search-box">
          <Search size={16} />
          <input value={search} onChange={(event) => { setSearch(event.target.value); resetPageAndSelection() }} placeholder="Search by title or transcript content…" aria-label="Search by title or transcript content" />
          {search && <button aria-label="Clear search" onClick={() => { setSearch(''); setDebouncedSearch(''); resetPageAndSelection() }}><span aria-hidden="true">×</span></button>}
        </label>
        <label className="history-filter"><Languages size={14} /><select value={language} onChange={(event) => { setLanguage(event.target.value); resetPageAndSelection() }} aria-label="Filter by language"><option value="">All languages</option>{(languageOptions.data ?? []).map((value) => <option value={value} key={value}>{value.toUpperCase()}</option>)}</select></label>
        <label className="history-filter"><CalendarDays size={14} /><select value={dateFilter} onChange={(event) => { setDateFilter(event.target.value as DateRangeFilter); resetPageAndSelection() }} aria-label="Filter by date"><option value="all">All time</option><option value="today">Today</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="year">This year</option></select></label>
        <label className="history-filter"><Clock3 size={14} /><select value={sortMode} onChange={(event) => { setSortMode(event.target.value as SortMode); resetPageAndSelection() }} aria-label="Sort sessions">{sortOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
        <button className="history-refresh" onClick={() => void refresh()} disabled={query.isFetching || statistics.isFetching} aria-label="Refresh sessions" title="Refresh"><RefreshCw size={15} className={query.isFetching ? 'is-spinning' : ''} /></button>
      </div>

      {selectedIds.length > 0 && <div className="history-bulk-toolbar"><span>{selectedIds.length} selected</span><div><button onClick={() => setDeleteTarget({ kind: 'bulk' })}><Trash2 size={13} />Delete selected</button><button onClick={() => setSelectedIds([])}>Clear selection</button></div></div>}

      <section className="history-table-card" aria-label="Saved transcription sessions">
        <div className="history-table-head"><label className="history-select-cell"><input type="checkbox" checked={allVisibleSelected} onChange={(event) => toggleVisible(event.target.checked)} aria-label="Select all visible sessions" /></label><span>Session / Transcript Preview</span><span>Language</span><span>Audio Recording</span><span>Duration</span><span>Created At</span><span>Actions</span></div>
        {query.isLoading ? <HistorySkeleton /> : query.isError ? <div className="history-state"><p>We couldn’t load your transcription history.</p><button className="history-retry" onClick={() => void query.refetch()}><RefreshCw size={13} />Try again</button></div> : records.length === 0 ? <HistoryEmptyState filtered={hasFilters} onClear={clearFilters} /> : <>
          {records.map((record) => <SessionRow
            key={record.id}
            record={record}
            selected={selectedIds.includes(record.id)}
            activeAudioId={activeAudioId}
            onSelect={toggleSelection}
            onActivateAudio={setActiveAudioId}
            onDeactivateAudio={(id) => setActiveAudioId((current) => current === id ? null : current)}
            onEdit={startEdit}
            onDelete={(item) => setDeleteTarget({ kind: 'single', record: item })}
            onCopy={(item) => void copyRecord(item)}
            onDownloadTranscript={downloadTranscript}
          />)}
          <div className="history-pagination"><span>{query.isFetching && !query.isLoading ? 'Updating… · ' : ''}Showing {firstItem}–{lastItem} of {totalCount} sessions</span><div className="history-page-buttons"><button disabled={page <= 1 || query.isFetching} aria-label="Previous page" onClick={() => changePage(page - 1)}><ChevronLeft size={15} /></button><span className="history-page-number">{page}</span><span>of {Math.max(totalPages, 1)}</span><button disabled={page >= totalPages || query.isFetching} aria-label="Next page" onClick={() => changePage(page + 1)}><ChevronRight size={15} /></button></div></div>
        </>}
      </section>

      {deleteTarget && <div className="history-confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setDeleteTarget(null) }}><section className="history-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="history-delete-title"><h2 id="history-delete-title">{deleteTarget.kind === 'bulk' ? `Delete ${selectedIds.length} sessions?` : 'Delete this session?'}</h2><p>This permanently removes the selected transcript and its archived original audio, if available.</p><div className="history-confirm-actions"><button onClick={() => setDeleteTarget(null)} disabled={busy}>Cancel</button><button className="confirm-danger" onClick={() => void confirmDelete()} disabled={busy}>{busy ? 'Deleting…' : 'Delete'}</button></div></section></div>}

      {editTarget && <div className="history-confirm-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) setEditTarget(null) }}><section className="history-confirm-dialog history-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="history-edit-title"><h2 id="history-edit-title">Edit session</h2><label>Title<input value={draftTitle} maxLength={200} onChange={(event) => setDraftTitle(event.target.value)} /></label><label>Transcript<textarea value={draftText} rows={8} onChange={(event) => setDraftText(event.target.value)} /></label><div className="history-confirm-actions"><button onClick={() => setEditTarget(null)} disabled={busy}>Cancel</button><button onClick={() => void saveEdit()} disabled={busy || !draftTitle.trim()}>{busy ? 'Saving…' : 'Save changes'}</button></div></section></div>}

      {toast && <div className="history-toast" role="status">{toast}</div>}
    </section>
  )
}
