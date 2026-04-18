import { useState, useEffect, useCallback } from 'react'
import { getHealth, getCacheStats, clearCache, ingestWikipedia } from '../api'
import { useToast } from './Toast'

function Section({ title, children }) {
  return (
    <div className="card space-y-4">
      <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">{title}</h2>
      {children}
    </div>
  )
}

function StatRow({ label, value, valueClass = 'text-gray-200' }) {
  return (
    <div className="flex items-center justify-between text-sm py-1 border-b border-gray-800 last:border-0">
      <span className="text-gray-500">{label}</span>
      <span className={`font-mono ${valueClass}`}>{value ?? '—'}</span>
    </div>
  )
}

export default function Settings() {
  const toast = useToast()
  const [health, setHealth]       = useState(null)
  const [cacheStats, setCache]    = useState(null)
  const [loadingHealth, setLoadingHealth] = useState(true)
  const [clearingCache, setClearingCache] = useState(false)
  const [wikiTopic, setWikiTopic] = useState('')
  const [wikiLang, setWikiLang]   = useState('en')
  const [wikiLoading, setWikiLoading] = useState(false)

  const reload = useCallback(async () => {
    setLoadingHealth(true)
    try {
      const [h, cs] = await Promise.all([getHealth(), getCacheStats()])
      setHealth(h)
      setCache(cs)
    } catch (e) {
      toast.error('Backend unreachable: ' + e.message)
    } finally {
      setLoadingHealth(false)
    }
  }, [toast])

  useEffect(() => { reload() }, [reload])

  async function handleClearCache() {
    setClearingCache(true)
    try {
      await clearCache()
      toast.success('Verification cache cleared')
      await reload()
    } catch (e) {
      toast.error('Failed to clear cache: ' + e.message)
    } finally {
      setClearingCache(false)
    }
  }

  async function handleWiki(e) {
    e.preventDefault()
    if (!wikiTopic.trim()) return
    setWikiLoading(true)
    try {
      const res = await ingestWikipedia(wikiTopic.trim(), wikiLang)
      if (res.chunks_added > 0) {
        toast.success(`Added ${res.chunks_added} chunks from "${res.topic}"`)
      } else {
        toast.error(`Wikipedia page not found: "${wikiTopic}"`)
      }
      setWikiTopic('')
    } catch (e) {
      toast.error('Wikipedia ingestion failed: ' + e.message)
    } finally {
      setWikiLoading(false)
    }
  }

  const kb  = health?.knowledge_base ?? {}
  const aud = health?.audit ?? {}

  return (
    <div className="space-y-5 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-gray-400 text-sm mt-1">System configuration and management tools.</p>
      </div>

      {/* System Status */}
      <Section title="System Status">
        {loadingHealth ? (
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-6 w-full" />)}
          </div>
        ) : health ? (
          <>
            <StatRow label="Backend" value="Online" valueClass="text-emerald-400" />
            <StatRow label="KB Collection"    value={kb.collection} />
            <StatRow label="KB Total Chunks"  value={kb.total_chunks?.toLocaleString()} valueClass="text-sky-300" />
            <StatRow label="BM25 Hybrid"      value={kb.bm25_enabled ? 'Enabled' : 'Disabled'} valueClass={kb.bm25_enabled ? 'text-emerald-400' : 'text-gray-500'} />
            <StatRow label="Total Requests"   value={aud.total_requests} />
            <StatRow label="Total Flagged"    value={aud.total_flagged} />
            <StatRow label="Blocked Responses" value={aud.blocked_responses} valueClass="text-red-400" />
          </>
        ) : (
          <p className="text-sm text-red-400">Backend offline — start with <code className="text-red-300">python run_proxy.py</code></p>
        )}
        <button onClick={reload} disabled={loadingHealth} className="btn-secondary text-xs py-1.5">
          {loadingHealth ? 'Refreshing…' : 'Refresh Status'}
        </button>
      </Section>

      {/* Thresholds */}
      {health && (
        <Section title="Detection Thresholds (read-only)">
          <p className="text-xs text-gray-600">
            Change these in your <code className="text-gray-400">.env</code> file and restart the server.
          </p>
          <StatRow
            label="Block Threshold"
            value={health.knowledge_base?.block_threshold ?? '0.25'}
            valueClass="text-red-400"
          />
          <StatRow
            label="Flag Threshold"
            value={health.knowledge_base?.flag_threshold ?? '0.60'}
            valueClass="text-yellow-400"
          />
          <StatRow
            label="KB Min Relevance"
            value={health.knowledge_base?.kb_min_relevance ?? '0.35'}
            valueClass="text-sky-300"
          />
        </Section>
      )}

      {/* Cache Management */}
      <Section title="Verification Cache">
        {cacheStats && (
          <div className="space-y-1">
            <StatRow label="Hit Rate"  value={cacheStats.hit_rate != null ? `${(cacheStats.hit_rate * 100).toFixed(1)}%` : '—'} valueClass="text-emerald-400" />
            <StatRow label="Cache Hits"   value={cacheStats.hits}   valueClass="text-emerald-400" />
            <StatRow label="Cache Misses" value={cacheStats.misses} />
          </div>
        )}
        <div className="flex gap-3 mt-2">
          <button
            onClick={handleClearCache}
            disabled={clearingCache}
            className="btn-danger flex items-center gap-2"
          >
            {clearingCache && <span className="spinner w-4 h-4 inline-block" />}
            {clearingCache ? 'Clearing…' : 'Clear Cache'}
          </button>
        </div>
        <p className="text-xs text-gray-600">
          Clearing the cache forces re-verification of all claims on next request.
        </p>
      </Section>

      {/* Wikipedia Quick Ingest */}
      <Section title="Wikipedia Quick Ingest">
        <p className="text-xs text-gray-500">
          Add a Wikipedia article to the knowledge base. Free, no API key required.
        </p>
        <form onSubmit={handleWiki} className="space-y-3">
          <div className="wiki-form flex-wrap gap-2">
            <input
              type="text"
              value={wikiTopic}
              onChange={(e) => setWikiTopic(e.target.value)}
              placeholder="e.g. Penicillin, Albert Einstein, GDPR"
              className="flex-1 min-w-[200px] bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-sky-600"
              required
            />
            <select
              value={wikiLang}
              onChange={(e) => setWikiLang(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-300 focus:outline-none"
            >
              <option value="en">English</option>
              <option value="de">German</option>
              <option value="fr">French</option>
              <option value="es">Spanish</option>
            </select>
          </div>
          <div className="flex flex-wrap gap-2">
            {['Penicillin', 'COVID-19 vaccine', 'GDPR', 'Machine learning'].map((t) => (
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
          <button type="submit" disabled={wikiLoading || !wikiTopic.trim()} className="btn-primary flex items-center gap-2">
            {wikiLoading && <span className="spinner w-4 h-4 inline-block" />}
            {wikiLoading ? 'Fetching…' : 'Ingest from Wikipedia'}
          </button>
        </form>
      </Section>

      {/* Quick links */}
      <Section title="Quick Links">
        <div className="flex flex-wrap gap-3">
          {[
            { label: 'Knowledge Base', href: '/knowledge-base' },
            { label: 'Audit Log',      href: '/audit' },
            { label: 'Dashboard',      href: '/dashboard' },
            { label: 'Playground',     href: '/playground' },
          ].map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="btn-secondary text-sm py-1.5"
            >
              {l.label}
            </a>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-2">
          Backend API docs: <a href="http://localhost:8080/docs" target="_blank" rel="noreferrer" className="text-sky-500 hover:underline">http://localhost:8080/docs</a>
        </p>
      </Section>
    </div>
  )
}
