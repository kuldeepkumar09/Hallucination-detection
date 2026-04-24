import { useState, useEffect, useRef, useCallback, Fragment } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { useToast } from './Toast'
import { getHealth } from '../api'

const BASE = import.meta.env.VITE_API_BASE ?? ''

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_BADGE = {
  verified:           'badge-verified',
  contradicted:       'badge-contradicted',
  partially_supported:'badge-flagged',
  unverifiable:       'badge-unverifiable',
}

const ACTION_BADGE = {
  block:    'action-block',
  flag:     'action-flag',
  annotate: 'action-annotate',
  pass:     'action-pass',
}

const ACTION_COLORS = {
  block:    '#f87171',
  flag:     '#fbbf24',
  annotate: '#38bdf8',
  pass:     '#6b7280',
}

const CATEGORY_BADGE = {
  MEDICAL:   'bg-red-900/60 text-red-300 border border-red-700',
  LEGAL:     'bg-purple-900/60 text-purple-300 border border-purple-700',
  FINANCIAL: 'bg-yellow-900/60 text-yellow-300 border border-yellow-700',
  GENERAL:   'bg-gray-800 text-gray-400 border border-gray-700',
}

const CONFIDENCE_COLOR = (c) => {
  if (c >= 0.8) return 'text-emerald-400'
  if (c >= 0.5) return 'text-yellow-400'
  return 'text-red-400'
}

const GAUGE_COLOR = (pct) => {
  if (pct >= 80) return '#34d399'
  if (pct >= 50) return '#fbbf24'
  return '#f87171'
}

const MAX_CHARS = 8000

const SAMPLE_TEXTS = [
  {
    label: 'Medical (errors)',
    text: `Penicillin, discovered by Alexander Fleming in 1928, revolutionised medicine. According to the WHO, diabetes currently affects approximately 500 million people worldwide. Ibuprofen is safe to use throughout all trimesters of pregnancy. The first COVID-19 vaccine authorised for emergency use was the Pfizer-BioNTech vaccine in December 2020.`,
  },
  {
    label: 'GDPR (errors)',
    text: `The EU GDPR came into force on 1 June 2019. Data breaches must be reported within 24 hours. The maximum penalty is 10 million EUR or 2% of annual turnover. All companies must appoint a Data Protection Officer without exception.`,
  },
  {
    label: 'Physics (subtle)',
    text: `Albert Einstein was born in Berlin, Germany on 14 March 1879. He published his Special Theory of Relativity in 1912. The speed of light is approximately 250,000 km/s. Einstein won the Nobel Prize in 1921 for his Theory of Relativity. The electron was discovered by J.J. Thomson in 1897.`,
  },
  {
    label: 'Tech (mostly correct)',
    text: `The World Wide Web was invented by Tim Berners-Lee in 1989. Google was founded by Larry Page and Sergey Brin in 1998. Apple was co-founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976. The first iPhone launched on 29 June 2007.`,
  },
]

// ── SVG Confidence Gauge ─────────────────────────────────────────────────────

function ConfidenceGauge({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const r = 50
  const cx = 68
  const cy = 62
  const circumference = Math.PI * r  // semicircle
  const offset = circumference - (pct / 100) * circumference
  const color = GAUGE_COLOR(pct)

  return (
    <div className="gauge-wrapper flex-col">
      <svg width="136" height="76" viewBox="0 0 136 76">
        {/* Track */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="#1f2937"
          strokeWidth="10"
          strokeLinecap="round"
        />
        {/* Fill — dash trick for animation */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.8s ease, stroke 0.5s ease' }}
        />
        <text x={cx} y={cy - 6} textAnchor="middle" fill={color} fontSize="20" fontWeight="bold" fontFamily="monospace">
          {pct}%
        </text>
        <text x={cx} y={cy + 11} textAnchor="middle" fill="#6b7280" fontSize="9" letterSpacing="1">
          CONFIDENCE
        </text>
      </svg>
    </div>
  )
}

// ── Skeleton ─────────────────────────────────────────────────────────────────

function ResultsSkeleton() {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="card space-y-2">
            <div className="skeleton h-8 w-16 mx-auto" />
            <div className="skeleton h-3 w-20 mx-auto" />
          </div>
        ))}
      </div>
      <div className="card space-y-3">
        <div className="skeleton h-4 w-40" />
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="skeleton h-6 w-full" style={{ animationDelay: `${i * 0.12}s` }} />
        ))}
      </div>
    </div>
  )
}

// ── Evidence Drawer ───────────────────────────────────────────────────────────

function EvidenceDrawer({ claim, onClose }) {
  return (
    <tr>
      <td colSpan={6} className="evidence-drawer">
        <div className="evidence-drawer-inner max-w-4xl">
          <div className="flex items-start justify-between mb-3">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Evidence Details</span>
            <button onClick={onClose} className="text-gray-600 hover:text-gray-300 text-xl leading-none bg-transparent border-0 cursor-pointer">
              &times;
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Claim</div>
              <p className="text-gray-200 leading-relaxed">{claim.text}</p>
              <button className="copy-btn mt-1" onClick={() => navigator.clipboard.writeText(claim.text)}>
                Copy
              </button>
            </div>
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Decision Reasoning</div>
              <p className="text-gray-300 leading-relaxed">{claim.annotation || '—'}</p>
            </div>
            {claim.key_evidence && (
              <div className="md:col-span-2">
                <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Key Evidence</div>
                <blockquote className="text-gray-300 border-l-2 border-sky-700 pl-3 italic leading-relaxed">
                  {claim.key_evidence}
                </blockquote>
                <button className="copy-btn mt-1" onClick={() => navigator.clipboard.writeText(claim.key_evidence)}>
                  Copy
                </button>
              </div>
            )}
            {claim.sources?.length > 0 && (
              <div className="md:col-span-2">
                <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">
                  Sources ({claim.sources.length})
                </div>
                <div className="flex flex-wrap gap-2">
                  {claim.sources.map((s, i) => (
                    <span key={i} className="source-chip" title={s}>{s}</span>
                  ))}
                </div>
              </div>
            )}
            {claim.rerank_scores?.length > 0 && (
              <div>
                <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Re-rank Scores</div>
                <div className="flex gap-2 flex-wrap">
                  {claim.rerank_scores.map((s, i) => (
                    <span key={i} className="text-xs font-mono text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
                      {s?.toFixed(3) ?? '—'}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  )
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function ActionTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <span style={{ color: d.payload.fill }} className="font-semibold">{d.name}</span>
      <span className="text-gray-300 ml-2">{d.value} claims</span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Playground() {
  const toast = useToast()
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [stage, setStage] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [expandedRow, setExpandedRow] = useState(null)
  const [showAnnotated, setShowAnnotated] = useState(false)
  const [apiKeySet, setApiKeySet] = useState(Boolean(localStorage.getItem('api_key')))
  const [streamedClaims, setStreamedClaims] = useState([])
  const [streamedProgress, setStreamedProgress] = useState({ total: 0, cached: 0, verified: 0 })
  const textareaRef = useRef(null)

  // Sync apiKeySet when localStorage changes (e.g. user saves key in Settings tab)
  useEffect(() => {
    const handler = () => setApiKeySet(Boolean(localStorage.getItem('api_key')))
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])
  const abortRef = useRef(null)

  // Elapsed timer while loading
  useEffect(() => {
    if (!loading) { setElapsed(0); return }
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [loading])

  const handleVerify = useCallback(async () => {
    if (!text.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    setExpandedRow(null)
    setShowAnnotated(false)
    setStreamedClaims([])
    setStreamedProgress({ total: 0, cached: 0, verified: 0 })

    const controller = new AbortController()
    abortRef.current = controller
    let retryCount = 0
    const MAX_RETRIES = 2

    const attemptVerify = async () => {
      setStage(retryCount > 0 ? `Retrying (${retryCount}/${MAX_RETRIES})…` : 'Connecting to pipeline…')

      const apiKey = localStorage.getItem('api_key') || ''
      const response = await fetch(`${BASE}/verify/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(apiKey ? { 'Authorization': `Bearer ${apiKey}` } : {}),
        },
        body: JSON.stringify({ text, model: 'playground' }),
        signal: controller.signal,
      })

      if (!response.ok) {
        let detail = `HTTP ${response.status}`
        try { detail = (await response.json()).detail || detail } catch {}
        throw new Error(detail)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.stage === 'done') {
              const data = event.result
              setResult(data)
              const n = data.total_claims ?? 0
              if (data.response_blocked) {
                toast.error(`Response blocked — ${data.block_reason || 'high risk claims detected'}`)
              } else if (n === 0) {
                toast.info('No factual claims detected in this text.')
              } else {
                toast.success(`${n} claim${n !== 1 ? 's' : ''} analysed in ${Math.round(data.processing_time_ms)}ms`)
              }
            } else if (event.stage === 'corrected') {
              if (event.corrected_text) {
                setResult(prev => prev ? { ...prev, corrected_text: event.corrected_text } : prev)
                setStage('Self-correction applied.')
              }
            } else if (event.stage === 'claim_verified') {
              const claim = event.claim || {}
              setStreamedClaims((prev) => {
                const updated = prev.filter((c) => c.id !== claim.id)
                return [...updated, {
                  ...claim,
                  status: event.status,
                  confidence: event.confidence,
                  cache_hit: event.cache_hit,
                  ensemble_used: event.ensemble_used,
                  key_evidence: event.key_evidence,
                }]
              })
              setStreamedProgress((prev) => ({
                total: prev.total + 1,
                cached: prev.cached + (event.cache_hit ? 1 : 0),
                verified: prev.verified + (event.status === 'verified' ? 1 : 0),
              }))
              setStage(`Verified ${event.status.replace('_', ' ')} — ${claim.normalized?.slice(0, 60) || ''}`)
            } else if (event.stage === 'error') {
              throw new Error(event.message || 'Pipeline error')
            } else if (event.message) {
              setStage(event.message)
            }
          } catch (parseErr) {
            if (parseErr.message !== 'Pipeline error' && !parseErr.message?.startsWith('HTTP')) continue
            throw parseErr
          }
        }
      }
    }

    try {
      await attemptVerify()
    } catch (e) {
      if (e.name === 'AbortError') {
        // User cancelled — do nothing
      } else if (retryCount < MAX_RETRIES && !controller.signal.aborted) {
        retryCount++
        try {
          await new Promise(resolve => setTimeout(resolve, 2000))
          await attemptVerify()
        } catch (retryErr) {
          if (retryErr.name !== 'AbortError') {
            setError(retryErr.message)
            toast.error(retryErr.message)
          }
        }
      } else {
        setError(e.message)
        toast.error(e.message)
      }
    } finally {
      setLoading(false)
      setStage('')
    }
  }, [text, loading, toast])

  // Keyboard shortcut: Ctrl/Cmd + Enter — declared after handleVerify to avoid TDZ error
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleVerify()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleVerify])

  const claims = result?.claims ?? []
  const blocked = claims.filter((c) => c.action === 'block').length
  const flagged  = claims.filter((c) => c.action === 'flag').length

  const actionData = claims.length
    ? Object.entries(
        claims.reduce((acc, c) => {
          acc[c.action] = (acc[c.action] || 0) + 1
          return acc
        }, {})
      ).map(([name, value]) => ({ name: name.toUpperCase(), value, fill: ACTION_COLORS[name] ?? '#6b7280' }))
    : []

  const charWarning = text.length > MAX_CHARS * 0.9
  const charColor   = text.length > MAX_CHARS ? 'text-red-400' : charWarning ? 'text-yellow-400' : 'text-gray-500'

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Playground</h1>
        <p className="text-gray-400 text-sm mt-1">
          Paste any LLM output to detect hallucinations via RAG verification.
          <span className="text-gray-600 ml-2">Ctrl+Enter to submit.</span>
        </p>
      </div>

      {/* API key warning banner */}
      {!apiKeySet && (
        <div className="card border-yellow-700 bg-yellow-950/30 text-yellow-300 text-sm flex items-center justify-between gap-3 py-3">
          <span>No API key configured — requests will fail with 401 Unauthorized.</span>
          <a href="/settings" className="btn-secondary text-xs py-1 shrink-0">Go to Settings →</a>
        </div>
      )}

      {/* Sample buttons */}
      <div className="flex flex-wrap gap-2">
        {SAMPLE_TEXTS.map((s) => (
          <button
            key={s.label}
            onClick={() => { setText(s.text); setResult(null); setError(null) }}
            className="btn-secondary text-xs py-1.5"
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Input card */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-300">LLM Output to Verify</label>
          {text && (
            <button
              className="copy-btn text-xs"
              onClick={() => { navigator.clipboard.writeText(text); toast.success('Copied to clipboard') }}
            >
              Copy
            </button>
          )}
        </div>
        <textarea
          ref={textareaRef}
          className="w-full h-44 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-sky-600 resize-none transition-colors"
          placeholder="Paste or type the LLM response you want to fact-check… (Ctrl+Enter to submit)"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS + 100))}
        />
        <div className="flex items-center gap-3">
          <button
            onClick={handleVerify}
            disabled={!text.trim() || loading || text.length > MAX_CHARS}
            className="btn-primary flex items-center gap-2"
          >
            {loading && <span className="spinner w-4 h-4 inline-block" />}
            {loading ? `Detecting… ${elapsed}s` : 'Detect Hallucinations'}
          </button>
          {text && !loading && (
            <button onClick={() => { setText(''); setResult(null); setError(null) }} className="btn-secondary text-sm">
              Clear
            </button>
          )}
          <span className={`text-xs ml-auto ${charColor}`}>
            {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
          </span>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="card border-red-800 bg-red-950/40 text-red-300 text-sm space-y-3">
          <p><strong>Error:</strong> {error}</p>
          {(error.includes('Invalid API key') || error.includes('401')) ? (
            <div className="text-xs text-gray-500 space-y-1 border-t border-gray-800 pt-3">
              <p className="font-medium text-gray-400">API key not set or incorrect.</p>
              <p>Go to <a href="/settings" className="text-sky-400 underline">Settings</a> and enter your API key (default: <code className="text-gray-300">hallu-dev-secret-2024</code>).</p>
            </div>
          ) : (error.includes('Failed to fetch') || error.includes('fetch') || error.includes('unreachable')) ? (
            <div className="text-xs text-gray-500 space-y-1 border-t border-gray-800 pt-3">
              <p className="font-medium text-gray-400">Backend is offline or still starting up.</p>
              <p>1. Start with: <code className="text-gray-300">docker compose up -d</code></p>
              <p>2. Wait ~30s for the model to load, then retry.</p>
            </div>
          ) : (
            <p className="text-red-400/70 text-xs">Make sure the backend is running at <code className="text-red-300">http://localhost:8080</code></p>
          )}
          <button onClick={handleVerify} disabled={loading} className="btn-secondary text-xs py-1">
            Retry
          </button>
        </div>
      )}

      {/* Skeleton while loading */}
      {loading && (
        <>
          <div className="flex flex-col items-center justify-center py-10 gap-4">
            <span className="spinner w-12 h-12 inline-block" style={{ borderWidth: 3 }} />
            <div className="text-center space-y-1">
              <p className="text-sm text-gray-300 font-medium">
                {stage || (elapsed < 15
                  ? 'Extracting claims from text…'
                  : elapsed < 45
                  ? 'Verifying claims against knowledge base…'
                  : elapsed < 90
                  ? 'Still working — verifying all claims…'
                  : `Running for ${elapsed}s — first run may take longer`)}
              </p>
              <p className="text-xs text-gray-500">
                {streamedProgress.total} claim(s) streamed, {streamedProgress.cached} cached, {streamedProgress.verified} verified so far.
              </p>
              {streamedClaims.length > 0 && (
                <div className="text-xs text-gray-400 space-y-1 mt-2">
                  <div className="font-semibold">Live claim stream</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-1 text-gray-300">
                    {streamedClaims.slice(-4).map((c, idx) => (
                      <span key={c.id || idx} className="inline-flex items-center gap-1 px-2 py-1 rounded bg-gray-900/80">
                        <strong>{c.status?.replace('_', ' ') || 'pending'}</strong>
                        <span className="truncate">{c.normalized?.slice(0, 40) || c.text?.slice(0, 40)}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {elapsed >= 60 && (
                <p className="text-xs text-gray-600">
                  NVIDIA NIM is processing — this can take up to 2 minutes on first run.
                </p>
              )}
            </div>
          </div>
          <ResultsSkeleton />
        </>
      )}

      {/* Results */}
      {result && !loading && (
        <>
          {/* Blocked banner */}
          {result.response_blocked && (
            <div className="card border-red-700 bg-red-950/50 text-red-300 text-sm font-semibold flex items-center gap-2">
              <span className="text-red-500 text-base">!</span>
              RESPONSE BLOCKED — {result.block_reason}
            </div>
          )}

          {/* Summary: KPI cards + Gauge + Donut */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            {[
              { label: 'Total Claims',  value: result.total_claims,   color: 'text-sky-300' },
              { label: 'Verified',      value: result.verified_count, color: 'text-emerald-400' },
              { label: 'Flagged',       value: result.flagged_count,  color: 'text-yellow-400' },
              { label: 'Blocked',       value: result.blocked_count,  color: 'text-red-400' },
            ].map((m) => (
              <div key={m.label} className="kpi-card text-center lg:col-span-1">
                <div className={`kpi-value ${m.color}`}>{m.value}</div>
                <div className="kpi-label">{m.label}</div>
              </div>
            ))}

            {/* Confidence Gauge */}
            <div className="card flex items-center justify-center lg:col-span-1 py-2">
              <ConfidenceGauge value={result.overall_confidence} />
            </div>

            {/* Action Donut */}
            {actionData.length > 0 && (
              <div className="card flex items-center justify-center lg:col-span-1 py-1">
                <ResponsiveContainer width={120} height={80}>
                  <PieChart>
                    <Pie
                      data={actionData}
                      cx="50%" cy="50%"
                      innerRadius={22} outerRadius={36}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {actionData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                    </Pie>
                    <Tooltip content={<ActionTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Meta bar */}
          <div className="flex flex-wrap gap-4 text-sm text-gray-400">
            <span>
              Confidence:{' '}
              <span className={`font-bold ${CONFIDENCE_COLOR(result.overall_confidence)}`}>
                {(result.overall_confidence * 100).toFixed(0)}%
              </span>
            </span>
            <span>
              Time: <span className="text-gray-200">{result.processing_time_ms?.toFixed(0)} ms</span>
            </span>
            {result.model && result.model !== 'playground' && (
              <span>Model: <span className="text-gray-300">{result.model}</span></span>
            )}
          </div>

          {/* Claims table */}
          {claims.length > 0 && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-300">
                  Claims Analysis ({claims.length})
                </h2>
                <button
                  className="copy-btn text-xs"
                  onClick={() => {
                    const txt = claims.map((c, i) => `${i+1}. [${c.action?.toUpperCase()}] ${c.text}`).join('\n')
                    navigator.clipboard.writeText(txt)
                    toast.success('Claims copied')
                  }}
                >
                  Copy all
                </button>
              </div>
              <div className="overflow-x-auto -mx-4 px-4" style={{ WebkitOverflowScrolling: 'touch' }}>
              <table className="w-full text-sm min-w-[640px]">
                <thead>
                  <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                    <th className="pb-2 pr-3 font-medium">Claim</th>
                    <th className="pb-2 pr-3 font-medium w-24">Type</th>
                    <th className="pb-2 pr-3 font-medium w-20">Stakes</th>
                    <th className="pb-2 pr-3 font-medium w-24">Category</th>
                    <th className="pb-2 pr-3 font-medium w-32">Status</th>
                    <th className="pb-2 pr-3 font-medium w-16 text-right">Conf.</th>
                    <th className="pb-2 font-medium w-20">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.map((c, i) => (
                    <Fragment key={c.id || i}>
                      <tr
                        className={`claim-row border-b border-gray-800/40 cursor-pointer hover:bg-gray-800/40 transition-colors ${
                          expandedRow === i ? 'bg-gray-800/40' : ''
                        }`}
                        style={{ animationDelay: `${i * 0.05}s` }}
                        onClick={() => setExpandedRow(expandedRow === i ? null : i)}
                      >
                        <td className="py-2 pr-3 text-gray-200 max-w-xs">
                          <span className="line-clamp-2 text-xs leading-relaxed">{c.text}</span>
                        </td>
                        <td className="py-2 pr-3 text-gray-400 text-xs">{c.type}</td>
                        <td className="py-2 pr-3 text-gray-400 text-xs">{c.stakes}</td>
                        <td className="py-2 pr-3">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${CATEGORY_BADGE[c.category] || CATEGORY_BADGE.GENERAL}`}>
                            {c.category || 'GENERAL'}
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <span className={STATUS_BADGE[c.status] || 'badge-unverifiable'}>
                            {c.status?.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className={`py-2 pr-3 text-right font-mono text-xs ${CONFIDENCE_COLOR(c.confidence)}`}>
                          {(c.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="py-2">
                          <span className={ACTION_BADGE[c.action] || 'action-pass'}>
                            {c.action?.toUpperCase()}
                          </span>
                        </td>
                      </tr>
                      {expandedRow === i && (
                        <EvidenceDrawer
                          claim={c}
                          onClose={() => setExpandedRow(null)}
                        />
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              </div>
              <p className="text-xs text-gray-700 mt-2">Click any row to expand evidence details.</p>
            </div>
          )}

          {/* Self-corrected output (shown first if available) */}
          {result.corrected_text && (
            <div className="card border-green-800">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-green-400 text-sm font-semibold">Auto-Corrected Response</span>
                  <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">Self-Correction Loop</span>
                </div>
                <button
                  className="copy-btn text-xs"
                  onClick={() => { navigator.clipboard.writeText(result.corrected_text); toast.success('Copied corrected text') }}
                >
                  Copy
                </button>
              </div>
              <pre className="whitespace-pre-wrap text-sm text-gray-200 font-sans leading-relaxed bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
                {result.corrected_text}
              </pre>
              <p className="text-xs text-gray-500 mt-2">
                The LLM silently fixed its own hallucinations using authoritative evidence from the knowledge base.
              </p>
            </div>
          )}

          {/* Before / After diff view */}
          {result.corrected_text && result.original_text && result.corrected_text.trim() !== result.original_text.trim() && (
            <div className="card border-gray-700">
              <h2 className="text-sm font-semibold text-gray-300 mb-3">Before / After Comparison</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-red-400 font-semibold mb-1">Original (with hallucinations)</p>
                  <pre className="whitespace-pre-wrap text-xs text-gray-400 font-sans leading-relaxed bg-red-950/20 border border-red-900/40 rounded-lg p-3 max-h-64 overflow-y-auto">
                    {result.original_text}
                  </pre>
                </div>
                <div>
                  <p className="text-xs text-green-400 font-semibold mb-1">Corrected (verified facts)</p>
                  <pre className="whitespace-pre-wrap text-xs text-gray-200 font-sans leading-relaxed bg-green-950/20 border border-green-900/40 rounded-lg p-3 max-h-64 overflow-y-auto">
                    {result.corrected_text}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* Annotated output */}
          {result.annotated_text && result.annotated_text !== text && (
            <div className="card">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-gray-300">Annotated Response</h2>
                <div className="flex items-center gap-3">
                  <button
                    className="copy-btn text-xs"
                    onClick={() => { navigator.clipboard.writeText(result.annotated_text); toast.success('Copied') }}
                  >
                    Copy
                  </button>
                  <button
                    className="btn-secondary text-xs py-1"
                    onClick={() => setShowAnnotated((v) => !v)}
                  >
                    {showAnnotated ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
              {showAnnotated && (
                <pre className="whitespace-pre-wrap text-sm text-gray-300 font-sans leading-relaxed bg-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto">
                  {result.annotated_text}
                </pre>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
