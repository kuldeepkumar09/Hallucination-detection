import { useState, useEffect, useCallback, useMemo } from 'react'
import { getKBStats, getKBDocuments, ingestText, ingestUrl, ingestWikipedia, deleteDocument } from '../api'
import { useToast } from './Toast'

// ── Confirm Delete Modal ──────────────────────────────────────────────────────

function ConfirmModal({ docId, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-semibold text-white mb-2">Delete Document?</h3>
        <p className="text-sm text-gray-400 mb-1">
          This will permanently remove all chunks for:
        </p>
        <p className="text-xs font-mono text-gray-300 bg-gray-800 px-3 py-2 rounded-lg mb-4 break-all">
          {docId}
        </p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="btn-secondary text-sm py-1.5">Cancel</button>
          <button onClick={onConfirm} className="btn-danger">Delete</button>
        </div>
      </div>
    </div>
  )
}

// ── Chunk bar ─────────────────────────────────────────────────────────────────

function ChunkBar({ value, max }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-gray-300 w-10 text-right">{value}</span>
      <div className="chunk-bar-track w-20">
        <div className="chunk-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function KnowledgeBase() {
  const toast = useToast()
  const [stats, setStats]     = useState(null)
  const [docs, setDocs]       = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('docs')  // 'docs' | 'text' | 'url' | 'wiki'
  const [confirmId, setConfirmId] = useState(null)

  // Add text
  const [addText, setAddText]     = useState('')
  const [addSource, setAddSource] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Add URL
  const [addUrl, setAddUrl]       = useState('')
  const [urlSource, setUrlSource] = useState('')

  // Wikipedia
  const [wikiTopic, setWikiTopic] = useState('')
  const [wikiLang, setWikiLang]   = useState('en')

  // Filters / sort
  const [search, setSearch]   = useState('')
  const [sortBy, setSortBy]   = useState('chunks_desc')

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const [s, d] = await Promise.all([getKBStats(), getKBDocuments()])
      setStats(s)
      setDocs(Array.isArray(d) ? d : [])
    } catch (e) {
      toast.error('Failed to load KB: ' + e.message)
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { reload() }, [reload])

  const maxChunks = useMemo(() => Math.max(...docs.map((d) => d.chunk_count || 0), 1), [docs])

  const filtered = useMemo(() => {
    let out = docs.filter((d) =>
      !search || d.source?.toLowerCase().includes(search.toLowerCase()) ||
      d.doc_id?.toLowerCase().includes(search.toLowerCase())
    )
    switch (sortBy) {
      case 'chunks_desc': out = [...out].sort((a, b) => (b.chunk_count || 0) - (a.chunk_count || 0)); break
      case 'chunks_asc':  out = [...out].sort((a, b) => (a.chunk_count || 0) - (b.chunk_count || 0)); break
      case 'source_asc':  out = [...out].sort((a, b) => (a.source || '').localeCompare(b.source || '')); break
      case 'source_desc': out = [...out].sort((a, b) => (b.source || '').localeCompare(a.source || '')); break
    }
    return out
  }, [docs, search, sortBy])

  async function handleDelete(docId) {
    try {
      const res = await deleteDocument(docId)
      toast.success(`Deleted ${res.deleted_chunks ?? '?'} chunks from "${docId}"`)
      await reload()
    } catch (e) {
      toast.error('Delete failed: ' + e.message)
    }
    setConfirmId(null)
  }

  async function handleAddText(e) {
    e.preventDefault()
    if (!addText.trim()) return
    setSubmitting(true)
    try {
      const res = await ingestText(addText, addSource || 'manual-upload')
      toast.success(`Added ${res.chunks_added} chunks from text`)
      setAddText(''); setAddSource('')
      await reload()
    } catch (e) {
      toast.error('Ingestion failed: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleAddUrl(e) {
    e.preventDefault()
    if (!addUrl.trim()) return
    let url = addUrl.trim()
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      toast.error('Please enter a valid URL starting with http:// or https://')
      return
    }
    setSubmitting(true)
    try {
      const res = await ingestUrl(url, urlSource || url)
      toast.success(`Added ${res.chunks_added} chunks from URL`)
      setAddUrl(''); setUrlSource('')
      await reload()
    } catch (e) {
      toast.error('URL ingestion failed: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleWiki(e) {
    e.preventDefault()
    if (!wikiTopic.trim()) return
    setSubmitting(true)
    try {
      const res = await ingestWikipedia(wikiTopic.trim(), wikiLang)
      if (res.chunks_added > 0) {
        toast.success(`Added ${res.chunks_added} chunks from Wikipedia: "${res.topic}"`)
      } else {
        toast.error(`Wikipedia page not found: "${wikiTopic}"`)
      }
      setWikiTopic('')
      await reload()
    } catch (e) {
      toast.error('Wikipedia ingestion failed: ' + e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const TABS = [
    { id: 'docs', label: `Documents (${docs.length})` },
    { id: 'text', label: 'Add Text' },
    { id: 'url',  label: 'Add URL' },
    { id: 'wiki', label: 'Wikipedia' },
  ]

  return (
    <div className="space-y-5">
      {confirmId && (
        <ConfirmModal
          docId={confirmId}
          onConfirm={() => handleDelete(confirmId)}
          onCancel={() => setConfirmId(null)}
        />
      )}

      <div>
        <h1 className="text-2xl font-bold text-white">Knowledge Base</h1>
        <p className="text-gray-400 text-sm mt-1">Manage authoritative documents used for hallucination verification.</p>
      </div>

      {/* Stats cards */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="kpi-card">
            <div className="kpi-value text-sky-300">{stats.total_chunks?.toLocaleString() ?? '—'}</div>
            <div className="kpi-label">Total Chunks</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-value text-violet-400">{docs.length}</div>
            <div className="kpi-label">Documents</div>
          </div>
          <div className="kpi-card">
            <div className={`kpi-value ${stats.bm25_enabled ? 'text-emerald-400' : 'text-gray-500'}`}>
              {stats.bm25_enabled ? 'ON' : 'OFF'}
            </div>
            <div className="kpi-label">BM25 Hybrid</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-value text-gray-300 text-sm truncate">{stats.collection ?? '—'}</div>
            <div className="kpi-label">Collection</div>
          </div>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-800 pb-0">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              activeTab === t.id
                ? 'bg-gray-900 text-sky-300 border-b-2 border-sky-500'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── DOCUMENTS tab ── */}
      {activeTab === 'docs' && (
        <div className="space-y-3">
          {/* Filter / sort bar */}
          <div className="filter-bar gap-3">
            <input
              type="text"
              placeholder="Filter by source or doc_id…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex-1 min-w-[200px] bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
            />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none"
            >
              <option value="chunks_desc">Chunks (most first)</option>
              <option value="chunks_asc">Chunks (least first)</option>
              <option value="source_asc">Source A-Z</option>
              <option value="source_desc">Source Z-A</option>
            </select>
            <span className="text-xs text-gray-600">{filtered.length} shown</span>
          </div>

          {loading ? (
            <div className="card space-y-2">
              {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-8 w-full" />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="card text-center text-gray-600 text-sm py-8">
              {search ? 'No documents match your filter.' : 'No documents ingested yet. Use Add Text, Add URL, or Wikipedia tabs.'}
            </div>
          ) : (
            <div className="card overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                    <th className="px-4 py-3 font-medium">Source</th>
                    <th className="px-4 py-3 font-medium w-40">Doc ID</th>
                    <th className="px-4 py-3 font-medium w-36">Chunks</th>
                    <th className="px-4 py-3 font-medium w-20">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((doc, i) => (
                    <tr key={doc.doc_id || i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                      <td className="px-4 py-2.5 text-gray-200 max-w-xs">
                        <span className="truncate block text-xs" title={doc.source}>{doc.source}</span>
                      </td>
                      <td className="px-4 py-2.5 text-gray-500 font-mono text-xs">
                        <span className="truncate block max-w-[140px]" title={doc.doc_id}>{doc.doc_id}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <ChunkBar value={doc.chunk_count || 0} max={maxChunks} />
                      </td>
                      <td className="px-4 py-2.5">
                        <button
                          onClick={() => setConfirmId(doc.doc_id)}
                          className="btn-danger py-1 px-2 text-xs"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── ADD TEXT tab ── */}
      {activeTab === 'text' && (
        <form onSubmit={handleAddText} className="card space-y-3 max-w-2xl">
          <h2 className="text-sm font-semibold text-gray-300">Ingest Plain Text</h2>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Source Name (optional)</label>
            <input
              type="text"
              value={addSource}
              onChange={(e) => setAddSource(e.target.value)}
              placeholder="e.g. company-policy-2024"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Content</label>
            <textarea
              value={addText}
              onChange={(e) => setAddText(e.target.value)}
              placeholder="Paste your authoritative text here…"
              className="w-full h-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600 resize-none"
              required
            />
          </div>
          <button type="submit" disabled={submitting || !addText.trim()} className="btn-primary flex items-center gap-2">
            {submitting && <span className="spinner w-4 h-4 inline-block" />}
            {submitting ? 'Ingesting…' : 'Ingest Text'}
          </button>
        </form>
      )}

      {/* ── ADD URL tab ── */}
      {activeTab === 'url' && (
        <form onSubmit={handleAddUrl} className="card space-y-3 max-w-2xl">
          <h2 className="text-sm font-semibold text-gray-300">Ingest from URL</h2>
          <div>
            <label className="text-xs text-gray-500 block mb-1">URL</label>
            <input
              type="url"
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              placeholder="https://example.com/article"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Source Label (optional)</label>
            <input
              type="text"
              value={urlSource}
              onChange={(e) => setUrlSource(e.target.value)}
              placeholder="e.g. WHO Guidelines"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
            />
          </div>
          <button type="submit" disabled={submitting || !addUrl.trim()} className="btn-primary flex items-center gap-2">
            {submitting && <span className="spinner w-4 h-4 inline-block" />}
            {submitting ? 'Fetching…' : 'Fetch & Ingest URL'}
          </button>
        </form>
      )}

      {/* ── WIKIPEDIA tab ── */}
      {activeTab === 'wiki' && (
        <form onSubmit={handleWiki} className="card space-y-4 max-w-2xl">
          <div>
            <h2 className="text-sm font-semibold text-gray-300">Wikipedia Ingestion</h2>
            <p className="text-xs text-gray-500 mt-1">
              Fetch a Wikipedia article and add it to the knowledge base. Free, no API key required.
            </p>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Article Title</label>
            <input
              type="text"
              value={wikiTopic}
              onChange={(e) => setWikiTopic(e.target.value)}
              placeholder="e.g. Penicillin, GDPR, Albert Einstein"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Language</label>
            <select
              value={wikiLang}
              onChange={(e) => setWikiLang(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none"
            >
              <option value="en">English (en)</option>
              <option value="de">German (de)</option>
              <option value="fr">French (fr)</option>
              <option value="es">Spanish (es)</option>
              <option value="ja">Japanese (ja)</option>
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            {['Penicillin', 'GDPR', 'Albert Einstein', 'COVID-19 vaccine', 'Machine learning'].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setWikiTopic(t)}
                className="filter-chip filter-chip-inactive text-xs"
              >
                {t}
              </button>
            ))}
          </div>
          <button type="submit" disabled={submitting || !wikiTopic.trim()} className="btn-primary flex items-center gap-2">
            {submitting && <span className="spinner w-4 h-4 inline-block" />}
            {submitting ? 'Fetching Wikipedia…' : 'Ingest from Wikipedia'}
          </button>
        </form>
      )}
    </div>
  )
}
