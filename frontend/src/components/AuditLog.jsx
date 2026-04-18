import { useState, useEffect, useCallback, useMemo } from 'react'
import { getAuditRecent } from '../api'
import { useToast } from './Toast'

const CONFIDENCE_COLOR = (c) => {
  if (c >= 0.8) return 'text-emerald-400'
  if (c >= 0.5) return 'text-yellow-400'
  return 'text-red-400'
}

const ACTION_FILTERS = ['ALL', 'BLOCK', 'FLAG', 'PASS']

function ClaimDetailRow({ claim, i }) {
  return (
    <tr className="border-b border-gray-800/40 text-xs">
      <td className="py-1.5 pr-3 text-gray-300 max-w-xs">
        <span className="line-clamp-2">{claim.text}</span>
      </td>
      <td className="py-1.5 pr-3 text-gray-500">{claim.type}</td>
      <td className="py-1.5 pr-3">
        <span className={`text-xs font-semibold ${
          claim.status === 'verified' ? 'text-emerald-400' :
          claim.status === 'contradicted' ? 'text-red-400' :
          claim.status === 'partially_supported' ? 'text-yellow-400' : 'text-gray-400'
        }`}>{claim.status?.replace('_', ' ')}</span>
      </td>
      <td className={`py-1.5 pr-3 font-mono ${CONFIDENCE_COLOR(claim.confidence)}`}>
        {claim.confidence != null ? `${(claim.confidence * 100).toFixed(0)}%` : '—'}
      </td>
      <td className="py-1.5">
        <span className={`font-bold text-xs ${
          claim.action === 'block'    ? 'text-red-400'    :
          claim.action === 'flag'     ? 'text-yellow-400' :
          claim.action === 'annotate' ? 'text-sky-400'    : 'text-gray-500'
        }`}>{claim.action?.toUpperCase()}</span>
      </td>
    </tr>
  )
}

function downloadJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function downloadCSV(entries, filename) {
  const cols = ['timestamp', 'model', 'total_claims', 'verified_count', 'flagged_count',
                 'blocked_count', 'overall_confidence', 'processing_time_ms', 'response_blocked']
  const lines = [cols.join(',')]
  entries.forEach((e) => {
    lines.push(cols.map((k) => JSON.stringify(e[k] ?? '')).join(','))
  })
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

export default function AuditLog() {
  const toast = useToast()
  const [entries, setEntries]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState(null)
  const [n, setN]                 = useState(50)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [expandedRow, setExpandedRow] = useState(null)
  const [actionFilter, setActionFilter] = useState('ALL')
  const [minConf, setMinConf]     = useState(0)
  const [maxConf, setMaxConf]     = useState(100)
  const [page, setPage]           = useState(1)
  const PAGE_SIZE = 20

  const load = useCallback(async () => {
    try {
      const data = await getAuditRecent(n)
      setEntries(Array.isArray(data) ? data : [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [n])

  useEffect(() => { setLoading(true); load() }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [autoRefresh, load])

  // Reset page when filter changes
  useEffect(() => { setPage(1) }, [actionFilter, minConf, maxConf])

  const filtered = useMemo(() => {
    return entries.filter((e) => {
      if (actionFilter !== 'ALL') {
        if (actionFilter === 'BLOCK' && !e.response_blocked && !e.blocked_count) return false
        if (actionFilter === 'FLAG'  && !e.flagged_count)  return false
        if (actionFilter === 'PASS'  && (e.blocked_count || e.flagged_count)) return false
      }
      const conf = (e.overall_confidence ?? 0) * 100
      if (conf < minConf || conf > maxConf) return false
      return true
    })
  }, [entries, actionFilter, minConf, maxConf])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated  = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const rowClass = (e) => {
    if (e.response_blocked) return 'audit-row-blocked'
    if ((e.flagged_count || 0) > 0) return 'audit-row-flagged'
    if ((e.blocked_count || 0) === 0 && (e.flagged_count || 0) === 0 && e.total_claims > 0) return 'audit-row-clean'
    return ''
  }

  function formatTime(ts) {
    try { return new Date(ts).toLocaleString() } catch { return ts ?? '—' }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Log</h1>
          <p className="text-gray-400 text-sm mt-1">
            {filtered.length} of {entries.length} entries
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            className="btn-export"
            onClick={() => {
              downloadJSON(filtered, `audit-${Date.now()}.json`)
              toast.success('Exported JSON')
            }}
          >
            Export JSON
          </button>
          <button
            className="btn-export"
            onClick={() => {
              downloadCSV(filtered, `audit-${Date.now()}.csv`)
              toast.success('Exported CSV')
            }}
          >
            Export CSV
          </button>
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-sky-500"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto (5s)
          </label>
        </div>
      </div>

      {/* Filter bar */}
      <div className="filter-bar flex-wrap gap-3">
        {/* Action chips */}
        <div className="flex gap-1">
          {ACTION_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setActionFilter(f)}
              className={`filter-chip ${actionFilter === f ? 'filter-chip-active' : 'filter-chip-inactive'}`}
            >
              {f}
            </button>
          ))}
        </div>

        {/* Confidence range */}
        <div className="flex items-center gap-2 text-xs text-gray-400 ml-2">
          <span>Conf:</span>
          <input
            type="number" min="0" max="100"
            value={minConf}
            onChange={(e) => setMinConf(Number(e.target.value))}
            className="w-12 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-200 focus:outline-none"
          />
          <span>–</span>
          <input
            type="number" min="0" max="100"
            value={maxConf}
            onChange={(e) => setMaxConf(Number(e.target.value))}
            className="w-12 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5 text-xs text-gray-200 focus:outline-none"
          />
          <span>%</span>
        </div>

        {/* Page size */}
        <div className="flex items-center gap-2 text-xs text-gray-400 ml-auto">
          <span>Load:</span>
          <select
            value={n}
            onChange={(e) => { setN(Number(e.target.value)); setPage(1) }}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-0.5 text-xs text-gray-200 focus:outline-none"
          >
            {[20, 50, 100, 200].map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
      </div>

      {error && (
        <div className="card border-red-800 bg-red-950/40 text-red-300 text-sm">
          Error loading audit log: {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="card space-y-2">
          {[0, 1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-8 w-full" />)}
        </div>
      ) : paginated.length === 0 ? (
        <div className="card text-center text-gray-600 text-sm py-8">
          {entries.length === 0 ? 'No audit entries yet. Run a verification to see results here.' : 'No entries match your filters.'}
        </div>
      ) : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full text-sm min-w-[720px]">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium w-28">Model</th>
                <th className="px-4 py-3 font-medium w-16 text-center">Claims</th>
                <th className="px-4 py-3 font-medium w-16 text-center">Flagged</th>
                <th className="px-4 py-3 font-medium w-16 text-center">Blocked</th>
                <th className="px-4 py-3 font-medium w-20 text-right">Conf.</th>
                <th className="px-4 py-3 font-medium w-20 text-right">Time</th>
                <th className="px-4 py-3 font-medium w-10"></th>
              </tr>
            </thead>
            <tbody>
              {paginated.map((entry, i) => {
                const isExp = expandedRow === i
                return (
                  <>
                    <tr
                      key={entry.request_id || i}
                      className={`border-b border-gray-800/40 cursor-pointer hover:bg-gray-800/30 transition-colors ${rowClass(entry)}`}
                      onClick={() => setExpandedRow(isExp ? null : i)}
                    >
                      <td className="px-4 py-2.5 text-gray-300 text-xs whitespace-nowrap">
                        {formatTime(entry.timestamp)}
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs truncate max-w-[100px]">
                        {entry.model || 'playground'}
                      </td>
                      <td className="px-4 py-2.5 text-center text-gray-200">{entry.total_claims ?? 0}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={entry.flagged_count ? 'text-yellow-400 font-semibold' : 'text-gray-600'}>
                          {entry.flagged_count ?? 0}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={entry.blocked_count ? 'text-red-400 font-bold' : 'text-gray-600'}>
                          {entry.blocked_count ?? 0}
                        </span>
                      </td>
                      <td className={`px-4 py-2.5 text-right font-mono text-xs ${CONFIDENCE_COLOR(entry.overall_confidence)}`}>
                        {entry.overall_confidence != null
                          ? `${(entry.overall_confidence * 100).toFixed(0)}%`
                          : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-400 text-xs">
                        {entry.processing_time_ms != null ? `${Math.round(entry.processing_time_ms)}ms` : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-gray-600 text-xs">
                        {isExp ? '▲' : '▼'}
                      </td>
                    </tr>
                    {isExp && entry.claims?.length > 0 && (
                      <tr key={`exp-${i}`}>
                        <td colSpan={8} className="px-4 py-3 bg-gray-800/40">
                          <div className="text-xs text-gray-400 mb-2">
                            Request ID: <span className="font-mono text-gray-300">{entry.request_id}</span>
                            {entry.response_blocked && (
                              <span className="ml-3 text-red-400 font-semibold">
                                BLOCKED — {entry.block_reason}
                              </span>
                            )}
                          </div>
                          <table className="w-full">
                            <thead>
                              <tr className="text-left text-xs text-gray-600 border-b border-gray-700">
                                <th className="pb-1.5 pr-3 font-medium">Claim</th>
                                <th className="pb-1.5 pr-3 font-medium w-24">Type</th>
                                <th className="pb-1.5 pr-3 font-medium w-32">Status</th>
                                <th className="pb-1.5 pr-3 font-medium w-16">Conf.</th>
                                <th className="pb-1.5 font-medium w-20">Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {entry.claims.map((c, j) => (
                                <ClaimDetailRow key={j} claim={c} i={j} />
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-secondary text-xs py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-gray-500 text-xs">
            Page {page} of {totalPages} ({filtered.length} entries)
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="btn-secondary text-xs py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
