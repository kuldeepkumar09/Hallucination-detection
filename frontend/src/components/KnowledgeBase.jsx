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
  const [wikiQuery, setWikiQuery]         = useState('')
  const [wikiTopic, setWikiTopic]         = useState('')
  const [wikiLang, setWikiLang]           = useState('en')
  const [wikiMode, setWikiMode]           = useState('full')
  const [wikiSearchResults, setWikiSearchResults] = useState([])
  const [wikiSearching, setWikiSearching] = useState(false)
  const [wikiPreview, setWikiPreview]     = useState(null)
  const [wikiPreviewing, setWikiPreviewing] = useState(false)

  // Filters / sort
  const [search, setSearch]   = useState('')
  const [sortBy, setSortBy]   = useState('chunks_desc')

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const [s, d] = await Promise.all([getKBStats(), getKBDocuments()])
      setStats(s)
      setDocs(Array.isArray(d) ? d : (d?.documents ?? []))
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

  async function handleWikiSearch(e) {
    e.preventDefault()
    if (!wikiQuery.trim()) return
    setWikiSearching(true)
    setWikiPreview(null)
    setWikiTopic('')
    try {
      const BASE = import.meta.env.VITE_API_BASE ?? ''
      const res = await fetch(`${BASE}/kb/search/wikipedia?q=${encodeURIComponent(wikiQuery)}&language=${wikiLang}&n=8`)
      const data = await res.json()
      setWikiSearchResults(data.results || [])
      if (!data.results?.length) toast.info('No Wikipedia results found.')
    } catch (e) {
      toast.error('Wikipedia search failed: ' + e.message)
    } finally {
      setWikiSearching(false)
    }
  }

  async function handleWikiPreview(title) {
    setWikiTopic(title)
    setWikiPreviewing(true)
    setWikiPreview(null)
    try {
      const BASE = import.meta.env.VITE_API_BASE ?? ''
      const res = await fetch(`${BASE}/kb/wikipedia/info?topic=${encodeURIComponent(title)}&language=${wikiLang}`)
      if (!res.ok) throw new Error('Page not found')
      const data = await res.json()
      setWikiPreview(data)
    } catch (e) {
      toast.error('Could not load Wikipedia preview: ' + e.message)
    } finally {
      setWikiPreviewing(false)
    }
  }

  async function handleWiki(e) {
    e.preventDefault()
    if (!wikiTopic.trim()) return
    setSubmitting(true)
    try {
      const res = await ingestWikipedia(wikiTopic.trim(), wikiLang, wikiMode)
      toast.success(`Added ${res.chunks_added} chunks from Wikipedia: "${res.topic}" (${wikiMode})`)
      setWikiQuery('')
      setWikiTopic('')
      setWikiPreview(null)
      setWikiSearchResults([])
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
        <div className="space-y-4 max-w-2xl">

          {/* Step 1 — Search */}
          <div className="card space-y-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-300">Wikipedia Search</h2>
              <p className="text-xs text-gray-500 mt-0.5">Search Wikipedia then preview and ingest any article. No API key required.</p>
            </div>
            <form onSubmit={handleWikiSearch} className="flex gap-2">
              <input
                type="text"
                value={wikiQuery}
                onChange={(e) => setWikiQuery(e.target.value)}
                placeholder="Search Wikipedia…"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
              />
              <select
                value={wikiLang}
                onChange={(e) => { setWikiLang(e.target.value); setWikiSearchResults([]); setWikiPreview(null) }}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none"
              >
                <option value="en">EN</option>
                <option value="de">DE</option>
                <option value="fr">FR</option>
                <option value="es">ES</option>
                <option value="hi">HI</option>
                <option value="ja">JA</option>
                <option value="zh">ZH</option>
              </select>
              <button type="submit" disabled={wikiSearching || !wikiQuery.trim()} className="btn-primary px-4">
                {wikiSearching ? <span className="spinner w-4 h-4 inline-block" /> : 'Search'}
              </button>
            </form>

            {/* Quick-pick chips */}
            <div className="flex flex-wrap gap-2">
              {['Albert Einstein', 'GDPR', 'Penicillin', 'COVID-19 vaccine', 'Machine learning', 'Python (programming)'].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => { setWikiQuery(t); setWikiTopic(t); handleWikiPreview(t) }}
                  className="filter-chip filter-chip-inactive text-xs"
                >
                  {t}
                </button>
              ))}
            </div>

            {/* Search results */}
            {wikiSearchResults.length > 0 && (
              <div className="space-y-1 border-t border-gray-800 pt-3">
                <p className="text-xs text-gray-500 mb-2">Click an article to preview it:</p>
                {wikiSearchResults.map((r) => (
                  <button
                    key={r.title}
                    type="button"
                    onClick={() => handleWikiPreview(r.title)}
                    className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                      wikiTopic === r.title
                        ? 'border-sky-600 bg-sky-900/20 text-sky-300'
                        : 'border-gray-700 bg-gray-800 text-gray-300 hover:border-gray-500'
                    }`}
                  >
                    <div className="font-medium">{r.title}</div>
                    {r.description && <div className="text-xs text-gray-500 truncate mt-0.5">{r.description}</div>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Step 2 — Preview + Ingest */}
          {(wikiPreviewing || wikiPreview || wikiTopic) && (
            <div className="card space-y-4">
              {wikiPreviewing && (
                <div className="flex items-center gap-2 text-gray-400 text-sm">
                  <span className="spinner w-4 h-4 inline-block" />
                  Loading preview…
                </div>
              )}

              {wikiPreview && (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-semibold text-white">{wikiPreview.title}</h3>
                      <a href={wikiPreview.url} target="_blank" rel="noreferrer" className="text-xs text-sky-500 hover:underline">
                        {wikiPreview.url}
                      </a>
                    </div>
                    <div className="text-right text-xs text-gray-500 shrink-0">
                      <div>{wikiPreview.section_count} sections</div>
                      <div>{(wikiPreview.text_length / 1000).toFixed(0)}k chars</div>
                    </div>
                  </div>

                  <p className="text-sm text-gray-300 leading-relaxed bg-gray-800 rounded-lg px-3 py-2">
                    {wikiPreview.summary}
                  </p>

                  {wikiPreview.sections?.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 mb-1">Sections:</p>
                      <div className="flex flex-wrap gap-1">
                        {wikiPreview.sections.slice(0, 12).map((s) => (
                          <span key={s} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded border border-gray-700">{s}</span>
                        ))}
                        {wikiPreview.sections.length > 12 && (
                          <span className="text-xs text-gray-600">+{wikiPreview.sections.length - 12} more</span>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Ingest form */}
              <form onSubmit={handleWiki} className="space-y-3 border-t border-gray-800 pt-3">
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="text-xs text-gray-500 block mb-1">Article to ingest</label>
                    <input
                      type="text"
                      value={wikiTopic}
                      onChange={(e) => setWikiTopic(e.target.value)}
                      placeholder="Article title"
                      className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
                      required
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Mode</label>
                    <select
                      value={wikiMode}
                      onChange={(e) => setWikiMode(e.target.value)}
                      className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none"
                    >
                      <option value="full">Full article</option>
                      <option value="summary">Summary only</option>
                    </select>
                  </div>
                </div>
                <div className="text-xs text-gray-500">
                  {wikiMode === 'full'
                    ? 'Ingests the entire article — best for thorough fact-checking.'
                    : 'Ingests only the intro paragraph — faster, less storage.'}
                </div>
                <button type="submit" disabled={submitting || !wikiTopic.trim()} className="btn-primary flex items-center gap-2">
                  {submitting && <span className="spinner w-4 h-4 inline-block" />}
                  {submitting ? 'Ingesting…' : `Ingest "${wikiTopic || 'article'}" (${wikiMode})`}
                </button>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
