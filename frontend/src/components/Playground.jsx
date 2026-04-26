import { useState, useEffect, useRef, useCallback } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { useToast } from './Toast'
import CascadePoint from './CascadePoint'
import FactualDiff from './FactualDiff'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const MAX_CHARS = 8000

// ── Color utilities ───────────────────────────────────────────────────────────

const STATUS_META = {
  verified:            { badge: 'badge-verified',     border: 'border-l-emerald-500', bg: 'bg-emerald-950/30', dot: '#34d399' },
  contradicted:        { badge: 'badge-contradicted', border: 'border-l-red-500',     bg: 'bg-red-950/30',     dot: '#f87171' },
  partially_supported: { badge: 'badge-flagged',      border: 'border-l-yellow-500',  bg: 'bg-yellow-950/20',  dot: '#fbbf24' },
  unverifiable:        { badge: 'badge-unverifiable', border: 'border-l-gray-600',    bg: 'bg-gray-900/50',    dot: '#6b7280' },
}

const ACTION_BADGE = {
  block:    'action-block',
  flag:     'action-flag',
  annotate: 'action-annotate',
  pass:     'action-pass',
}

const ACTION_COLORS = {
  block: '#f87171', flag: '#fbbf24', annotate: '#38bdf8', pass: '#6b7280',
}

const CATEGORY_BADGE = {
  MEDICAL:   'bg-red-900/60 text-red-300 border border-red-800',
  LEGAL:     'bg-purple-900/60 text-purple-300 border border-purple-800',
  FINANCIAL: 'bg-yellow-900/60 text-yellow-300 border border-yellow-800',
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

// ── Sample texts ──────────────────────────────────────────────────────────────

const SAMPLE_TEXTS = [
  {
    label: '🩺 Medical',
    text: `Penicillin, discovered by Alexander Fleming in 1928, revolutionised medicine. According to the WHO, diabetes currently affects approximately 500 million people worldwide. Ibuprofen is safe to use throughout all trimesters of pregnancy. The first COVID-19 vaccine authorised for emergency use was the Pfizer-BioNTech vaccine in December 2020.`,
  },
  {
    label: '⚖️ GDPR',
    text: `The EU GDPR came into force on 1 June 2019. Data breaches must be reported within 24 hours. The maximum penalty is 10 million EUR or 2% of annual turnover. All companies must appoint a Data Protection Officer without exception.`,
  },
  {
    label: '⚛️ Physics',
    text: `Albert Einstein was born in Berlin, Germany on 14 March 1879. He published his Special Theory of Relativity in 1912. The speed of light is approximately 250,000 km/s. Einstein won the Nobel Prize in 1921 for his Theory of Relativity. The electron was discovered by J.J. Thomson in 1897.`,
  },
  {
    label: '💻 Tech',
    text: `The World Wide Web was invented by Tim Berners-Lee in 1989. Google was founded by Larry Page and Sergey Brin in 1998. Apple was co-founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976. The first iPhone launched on 29 June 2007.`,
  },
]

// ── Pipeline stages ───────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { id: 'coref',   label: 'Coref',   icon: '🔗', keywords: ['coref', 'resolv', 'pronoun'] },
  { id: 'extract', label: 'Extract', icon: '🔍', keywords: ['extract', 'claim', 'parsing'] },
  { id: 'nli',     label: 'NLI',     icon: '🧠', keywords: ['nli', 'infer', 'deberta', 'scor'] },
  { id: 'rag',     label: 'RAG',     icon: '📚', keywords: ['retriev', 'knowl', 'rag', 'bm25', 'hybrid', 'rerank'] },
  { id: 'verify',  label: 'Verify',  icon: '⚡', keywords: ['verif', 'llm', 'cross', 'claim_verified'] },
  { id: 'hmm',     label: 'HMM',     icon: '📊', keywords: ['hmm', 'cascade', 'sequence', 'reliab'] },
  { id: 'correct', label: 'Fix',     icon: '✨', keywords: ['correct', 'rewrit', 'self-correct'] },
]

function getActiveStage(msg) {
  if (!msg) return 1
  const lower = msg.toLowerCase()
  for (let i = PIPELINE_STAGES.length - 1; i >= 0; i--) {
    if (PIPELINE_STAGES[i].keywords.some(kw => lower.includes(kw))) return i
  }
  return 1
}

// ── Pipeline Visualization ────────────────────────────────────────────────────

function PipelineViz({ stageMsg, streamedProgress }) {
  const activeIdx = getActiveStage(stageMsg)

  return (
    <div className="space-y-3">
      <div className="flex items-start">
        {PIPELINE_STAGES.map((stage, i) => {
          const isDone = i < activeIdx
          const isActive = i === activeIdx
          const isLast = i === PIPELINE_STAGES.length - 1

          return (
            <div key={stage.id} className="flex flex-col items-center flex-1 relative">
              {/* Connector line between dots */}
              {!isLast && (
                <div
                  className="absolute top-3.5 left-1/2 w-full h-0.5 transition-all duration-700"
                  style={{
                    background: isDone
                      ? 'linear-gradient(90deg, #34d399, #38bdf8)'
                      : 'rgba(255,255,255,0.06)',
                  }}
                />
              )}
              {/* Stage dot */}
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold relative z-10 transition-all duration-500 ${
                  isDone
                    ? 'bg-emerald-900 border border-emerald-600 text-emerald-300'
                    : isActive
                    ? 'bg-sky-900 border-2 border-sky-400 text-sky-200 pipeline-dot-active'
                    : 'bg-gray-900 border border-gray-800 text-gray-700'
                }`}
              >
                {isDone ? '✓' : stage.icon}
              </div>
              {/* Label */}
              <span
                className="mt-1.5 text-center transition-colors duration-300"
                style={{
                  fontSize: 9,
                  color: isDone ? '#059669' : isActive ? '#38bdf8' : '#374151',
                }}
              >
                {stage.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      {streamedProgress.total > 0 && (
        <div className="flex items-center gap-3 text-xs text-gray-600">
          <div className="flex-1 h-1 bg-gray-900 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${Math.min(100, (streamedProgress.verified / Math.max(streamedProgress.total, 1)) * 100)}%`,
                background: 'linear-gradient(90deg, #0ea5e9, #34d399)',
              }}
            />
          </div>
          <span>{streamedProgress.total} claims streaming</span>
        </div>
      )}
    </div>
  )
}

// ── Trust Score Gauge ─────────────────────────────────────────────────────────

function TrustScore({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const r = 46
  const cx = 60
  const cy = 60
  const circumference = Math.PI * r
  const offset = circumference - (pct / 100) * circumference
  const color = GAUGE_COLOR(pct)

  return (
    <div className="flex flex-col items-center">
      <svg width="120" height="72" viewBox="0 0 120 72">
        {/* Track */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="10" strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${circumference}`}
          strokeDashoffset={offset}
          style={{
            transition: 'stroke-dashoffset 1s cubic-bezier(0.34, 1.56, 0.64, 1), stroke 0.5s',
            filter: `drop-shadow(0 0 6px ${color}80)`,
          }}
        />
        <text x={cx} y={cy - 8} textAnchor="middle" fill={color} fontSize="22" fontWeight="bold" fontFamily="monospace">
          {pct}%
        </text>
        <text x={cx} y={cy + 8} textAnchor="middle" fill="#374151" fontSize="8" letterSpacing="2">
          TRUST
        </text>
      </svg>
    </div>
  )
}

// ── Quick Feedback ─────────────────────────────────────────────────────────────

function QuickFeedback({ claimId }) {
  const [sent, setSent] = useState(null)

  const submit = async (isCorrect) => {
    if (sent !== null) return
    setSent(isCorrect)
    try {
      await fetch(`${BASE}/audit/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ claim_id: claimId, is_correct: isCorrect }),
      })
    } catch { setSent(null) }
  }

  if (sent === true)  return <span className="text-xs text-emerald-500 font-medium">✓ Correct</span>
  if (sent === false) return <span className="text-xs text-red-500 font-medium">✗ Incorrect</span>

  return (
    <span className="inline-flex gap-2">
      <button
        onClick={() => submit(true)}
        className="text-xs text-gray-600 hover:text-emerald-400 transition-colors px-2 py-0.5 border border-gray-800 hover:border-emerald-800 rounded"
      >✓</button>
      <button
        onClick={() => submit(false)}
        className="text-xs text-gray-600 hover:text-red-400 transition-colors px-2 py-0.5 border border-gray-800 hover:border-red-800 rounded"
      >✗</button>
    </span>
  )
}

// ── Claim Card ────────────────────────────────────────────────────────────────

function ClaimCard({ claim, index, isExpanded, onToggle }) {
  const meta = STATUS_META[claim.status] || STATUS_META.unverifiable
  const conf = Math.round((claim.confidence ?? 0) * 100)

  return (
    <div
      className={`border-l-4 ${meta.border} ${meta.bg} rounded-r-xl p-4 cursor-pointer transition-all duration-200 hover:brightness-110 claim-card-new`}
      style={{ animationDelay: `${index * 0.07}s` }}
      onClick={onToggle}
    >
      <div className="flex items-start gap-3">
        {/* Left: badges + text + confidence bar */}
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className={meta.badge}>{claim.status?.replace(/_/g, ' ')}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${CATEGORY_BADGE[claim.category] || CATEGORY_BADGE.GENERAL}`}>
              {claim.category || 'GENERAL'}
            </span>
            {claim.cache_hit    && <span className="text-xs text-sky-700 font-semibold">⚡ cached</span>}
            {claim.ensemble_used && <span className="text-xs text-violet-500 font-semibold">🎯 ensemble</span>}
          </div>
          <p className="text-sm text-gray-200 leading-relaxed">{claim.text}</p>
          {/* Confidence bar */}
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1.5 bg-gray-900 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${conf}%`,
                  background: `linear-gradient(90deg, ${GAUGE_COLOR(conf)}, ${GAUGE_COLOR(conf)}99)`,
                }}
              />
            </div>
            <span className={`text-xs font-mono font-bold ${CONFIDENCE_COLOR(claim.confidence)}`}>{conf}%</span>
          </div>
        </div>

        {/* Right: action badge + expand toggle */}
        <div className="flex-shrink-0 flex flex-col items-center gap-2 pt-0.5">
          <span className={ACTION_BADGE[claim.action] || 'action-pass'}>{claim.action?.toUpperCase()}</span>
          <span className="text-gray-700 text-xs select-none">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* Expanded evidence */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-white/5 space-y-3">
          {claim.annotation && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Reasoning</div>
              <p className="text-xs text-gray-300 leading-relaxed">{claim.annotation}</p>
            </div>
          )}
          {claim.key_evidence && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Key Evidence</div>
              <blockquote className="text-xs text-gray-300 border-l-2 border-sky-800/60 pl-3 italic leading-relaxed">
                "{claim.key_evidence}"
              </blockquote>
            </div>
          )}
          {claim.sources?.length > 0 && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Sources ({claim.sources.length})</div>
              <div className="flex flex-wrap gap-1.5">
                {claim.sources.map((s, i) => (
                  <span key={i} className="source-chip">{s}</span>
                ))}
              </div>
            </div>
          )}
          {claim.rerank_scores?.length > 0 && (
            <div>
              <div className="text-xs text-gray-600 uppercase tracking-wider mb-1">Re-rank Scores</div>
              <div className="flex gap-2 flex-wrap">
                {claim.rerank_scores.map((s, i) => (
                  <span key={i} className="text-xs font-mono text-gray-500 bg-gray-900 px-2 py-0.5 rounded">
                    {s?.toFixed(3) ?? '—'}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="flex items-center gap-2 pt-1">
            <span className="text-xs text-gray-600">Verdict correct?</span>
            <QuickFeedback claimId={claim.id} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function ResultsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map(i => (
          <div key={i} className="card space-y-2 py-5">
            <div className="skeleton h-8 w-12 mx-auto" />
            <div className="skeleton h-3 w-20 mx-auto" />
          </div>
        ))}
      </div>
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="skeleton h-20 w-full rounded-xl" style={{ animationDelay: `${i * 0.1}s` }} />
      ))}
    </div>
  )
}

// ── Action Tooltip ────────────────────────────────────────────────────────────

function ActionTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <span style={{ color: d.payload.fill }} className="font-semibold">{d.name}</span>
      <span className="text-gray-300 ml-2">{d.value} claims</span>
    </div>
  )
}

// ── Welcome Screen ────────────────────────────────────────────────────────────

function WelcomeScreen() {
  const features = [
    { icon: '🔍', title: 'Claim Extraction',   desc: 'Llama 3.1-8B extracts every verifiable factual claim' },
    { icon: '📚', title: 'Hybrid RAG',          desc: 'BM25 + vector search across 50K+ knowledge chunks' },
    { icon: '🧠', title: 'DeBERTa NLI',         desc: 'Neural inference scores semantic entailment on GPU' },
    { icon: '⚡', title: 'LLM Verification',    desc: 'Llama 3.3-70B cross-checks each claim with evidence' },
    { icon: '📊', title: 'HMM Cascade',         desc: 'Hidden Markov Model detects hallucination sequences' },
    { icon: '✨', title: 'Self-Correction',      desc: 'Automatically rewrites hallucinations using verified facts' },
  ]

  return (
    <div className="space-y-5 py-1">
      <p className="text-gray-600 text-sm">Select a sample above or paste text → hit Detect.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {features.map((f, i) => (
          <div
            key={i}
            className="card hover:border-gray-700 transition-colors claim-card-new"
            style={{ animationDelay: `${i * 0.06}s` }}
          >
            <div className="flex items-start gap-3">
              <span className="text-xl flex-shrink-0">{f.icon}</span>
              <div>
                <div className="text-sm font-semibold text-gray-300">{f.title}</div>
                <div className="text-xs text-gray-600 mt-0.5 leading-relaxed">{f.desc}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function Playground() {
  const toast = useToast()
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [stage, setStage] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [expandedRow, setExpandedRow] = useState(null)
  const [apiKeySet, setApiKeySet] = useState(Boolean(localStorage.getItem('api_key')))
  const [streamedClaims, setStreamedClaims] = useState([])
  const [streamedProgress, setStreamedProgress] = useState({ total: 0, cached: 0, verified: 0 })
  const abortRef = useRef(null)

  useEffect(() => {
    const handler = () => setApiKeySet(Boolean(localStorage.getItem('api_key')))
    window.addEventListener('storage', handler)
    return () => window.removeEventListener('storage', handler)
  }, [])

  useEffect(() => {
    if (!loading) { setElapsed(0); return }
    const id = setInterval(() => setElapsed(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [loading])

  const handleVerify = useCallback(async () => {
    if (!text.trim() || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    setExpandedRow(null)
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
                toast.success(`${n} claim${n !== 1 ? 's' : ''} verified in ${Math.round(data.processing_time_ms)}ms`)
              }
            } else if (event.stage === 'corrected') {
              if (event.corrected_text) {
                setResult(prev => prev ? { ...prev, corrected_text: event.corrected_text } : prev)
                setStage('Self-correction applied.')
              }
            } else if (event.stage === 'claim_verified') {
              const claim = event.claim || {}
              setStreamedClaims(prev => {
                const updated = prev.filter(c => c.id !== claim.id)
                return [...updated, {
                  ...claim,
                  status:        event.status,
                  confidence:    event.confidence,
                  cache_hit:     event.cache_hit,
                  ensemble_used: event.ensemble_used,
                  key_evidence:  event.key_evidence,
                }]
              })
              setStreamedProgress(prev => ({
                total:    prev.total + 1,
                cached:   prev.cached + (event.cache_hit ? 1 : 0),
                verified: prev.verified + (event.status === 'verified' ? 1 : 0),
              }))
              setStage(`Verified ${event.status?.replace('_', ' ')} — ${claim.normalized?.slice(0, 55) || ''}`)
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
        // user cancelled — silent
      } else if (retryCount < MAX_RETRIES && !controller.signal.aborted) {
        retryCount++
        try {
          await new Promise(r => setTimeout(r, 2000))
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

  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleVerify()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleVerify])

  const claims = result?.claims ?? []
  const actionData = claims.length
    ? Object.entries(
        claims.reduce((acc, c) => { acc[c.action] = (acc[c.action] || 0) + 1; return acc }, {})
      ).map(([name, value]) => ({ name: name.toUpperCase(), value, fill: ACTION_COLORS[name] ?? '#6b7280' }))
    : []

  const charWarning = text.length > MAX_CHARS * 0.9
  const charColor   = text.length > MAX_CHARS ? 'text-red-400' : charWarning ? 'text-yellow-400' : 'text-gray-600'
  const hasResults  = result && !loading

  return (
    <div className="space-y-5">

      {/* ── Page Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold gradient-text">Hallucination Detection</h1>
          <p className="text-gray-600 text-sm mt-1">
            7-stage AI pipeline · RAG · NLI · HMM · Self-Correction · Free LLMs
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            { label: '7 Stages',    color: 'text-sky-400'    },
            { label: 'NVIDIA NIM',  color: 'text-emerald-400' },
            { label: 'Live Stream', color: 'text-violet-400'  },
          ].map(p => (
            <span key={p.label} className={`stats-pill ${p.color}`}>{p.label}</span>
          ))}
        </div>
      </div>

      {/* ── API Key Warning ── */}
      {!apiKeySet && (
        <div className="card border-yellow-800/60 bg-yellow-950/20 text-yellow-400 text-sm flex items-center justify-between gap-3 py-3">
          <span>⚠ No API key configured — requests will fail with 401.</span>
          <a href="/settings" className="btn-secondary text-xs py-1 shrink-0">Settings →</a>
        </div>
      )}

      {/* ── Sample Texts ── */}
      <div className="flex flex-wrap gap-2">
        {SAMPLE_TEXTS.map(s => (
          <button
            key={s.label}
            onClick={() => { setText(s.text); setResult(null); setError(null) }}
            className="btn-secondary text-xs py-1.5"
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* ── Split Panel (input | results) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* LEFT — Input */}
        <div className="space-y-4">
          <div className="card space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-semibold text-gray-300">LLM Output to Verify</label>
              <span className={`text-xs font-mono ${charColor}`}>
                {text.length.toLocaleString()} / {MAX_CHARS.toLocaleString()}
              </span>
            </div>
            <textarea
              className="w-full h-52 bg-gray-950/80 border border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-100 placeholder-gray-700 focus:outline-none focus:border-sky-700/80 resize-none transition-colors leading-relaxed"
              placeholder={`Paste or type the LLM response you want to fact-check…\n\nTry a sample above, or press Ctrl+Enter to submit.`}
              value={text}
              onChange={e => setText(e.target.value.slice(0, MAX_CHARS + 100))}
            />
            <div className="flex items-center gap-3 flex-wrap">
              <button
                onClick={handleVerify}
                disabled={!text.trim() || loading || text.length > MAX_CHARS}
                className="btn-primary flex items-center gap-2"
              >
                {loading && <span className="spinner w-4 h-4 inline-block" />}
                {loading ? `Analysing… ${elapsed}s` : '🔬 Detect Hallucinations'}
              </button>
              {loading && (
                <button
                  onClick={() => { abortRef.current?.abort(); setLoading(false) }}
                  className="btn-secondary text-xs py-1.5"
                >
                  Cancel
                </button>
              )}
              {text && !loading && (
                <button
                  onClick={() => { setText(''); setResult(null); setError(null) }}
                  className="btn-secondary text-sm"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Pipeline visualization — only while loading */}
          {loading && (
            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                  Pipeline Progress
                </span>
                <span className="text-xs text-gray-700 font-mono">{elapsed}s</span>
              </div>

              <PipelineViz stageMsg={stage} streamedProgress={streamedProgress} />

              <p className="text-xs text-gray-600 min-h-[2.5rem] leading-relaxed">
                {stage || (
                  elapsed < 15 ? 'Extracting factual claims from text…' :
                  elapsed < 45 ? 'Verifying claims against knowledge base…' :
                  elapsed < 90 ? 'All stages running — longer texts take more time…' :
                  `Running ${elapsed}s — NIM may need a moment to warm up on first call.`
                )}
              </p>

              {/* Live claim stream preview */}
              {streamedClaims.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs text-gray-700 uppercase tracking-wider">Live stream</div>
                  {streamedClaims.slice(-3).map((c, i) => {
                    const meta = STATUS_META[c.status] || STATUS_META.unverifiable
                    return (
                      <div
                        key={c.id || i}
                        className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg ${meta.bg} claim-card-new`}
                        style={{ animationDelay: `${i * 0.05}s` }}
                      >
                        <span className={meta.badge}>{c.status?.replace(/_/g, ' ')}</span>
                        <span className="text-gray-400 truncate">
                          {c.normalized?.slice(0, 65) || c.text?.slice(0, 65)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}

          {/* Error card */}
          {error && (
            <div className="card border-red-900/60 bg-red-950/30 text-red-300 text-sm space-y-3">
              <p><strong>Error:</strong> {error}</p>
              {(error.includes('401') || error.includes('Invalid API')) ? (
                <p className="text-xs text-gray-600">
                  Go to <a href="/settings" className="text-sky-400 underline">Settings</a> and enter your API key
                  (from your <code className="text-gray-400">.env</code> as <code className="text-gray-400">API_KEY=hallu-dev-secret-2024</code>).
                </p>
              ) : (error.includes('fetch') || error.includes('unreachable')) ? (
                <div className="text-xs text-gray-600 space-y-1">
                  <p className="text-gray-400 font-medium">Backend is offline or starting up.</p>
                  <code className="block bg-gray-900 rounded px-2 py-1 text-gray-300 font-mono text-xs">
                    docker compose up -d
                  </code>
                </div>
              ) : null}
              <button onClick={handleVerify} disabled={loading} className="btn-secondary text-xs py-1">
                Retry
              </button>
            </div>
          )}
        </div>

        {/* RIGHT — Results */}
        <div className="space-y-4">
          {!loading && !result && !error && <WelcomeScreen />}
          {loading && !result && <ResultsSkeleton />}

          {hasResults && (
            <>
              {/* Blocked banner */}
              {result.response_blocked && (
                <div className="card border-red-700 bg-red-950/50 text-red-300 text-sm font-semibold flex items-center gap-2">
                  <span className="text-red-400">⛔</span>
                  RESPONSE BLOCKED — {result.block_reason}
                </div>
              )}

              {/* KPI cards + Trust Score */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Total',    value: result.total_claims,   color: 'text-sky-300'    },
                  { label: 'Verified', value: result.verified_count, color: 'text-emerald-400' },
                  { label: 'Flagged',  value: result.flagged_count,  color: 'text-yellow-400'  },
                  { label: 'Blocked',  value: result.blocked_count,  color: 'text-red-400'     },
                  { label: 'Time ms',  value: result.processing_time_ms?.toFixed(0), color: 'text-gray-400' },
                ].map(m => (
                  <div key={m.label} className="kpi-card text-center">
                    <div className={`kpi-value ${m.color}`}>{m.value}</div>
                    <div className="kpi-label">{m.label}</div>
                  </div>
                ))}
                <div className="card flex items-center justify-center">
                  <TrustScore value={result.overall_confidence} />
                </div>
              </div>

              {/* Action distribution */}
              {actionData.length > 0 && (
                <div className="card flex items-center justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="text-xs text-gray-600 uppercase tracking-wider mb-2">Action Distribution</div>
                    {actionData.map(d => (
                      <div key={d.name} className="flex items-center gap-2 text-xs">
                        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: d.fill }} />
                        <span className="text-gray-400">{d.name}</span>
                        <span className="text-gray-300 font-mono ml-auto pl-4">{d.value}</span>
                      </div>
                    ))}
                  </div>
                  <ResponsiveContainer width={90} height={80}>
                    <PieChart>
                      <Pie
                        data={actionData}
                        cx="50%" cy="50%"
                        innerRadius={22} outerRadius={38}
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

              {/* Claim cards */}
              {claims.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Claims ({claims.length}) — click to expand
                    </span>
                    <button
                      className="copy-btn text-xs"
                      onClick={() => {
                        const txt = claims.map((c, i) => `${i + 1}. [${c.action?.toUpperCase()}] ${c.text}`).join('\n')
                        navigator.clipboard.writeText(txt)
                        toast.success('Claims copied to clipboard')
                      }}
                    >
                      Copy all
                    </button>
                  </div>
                  {claims.map((c, i) => (
                    <ClaimCard
                      key={c.id || i}
                      claim={c}
                      index={i}
                      isExpanded={expandedRow === i}
                      onToggle={() => setExpandedRow(expandedRow === i ? null : i)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Full-width: Self-correction + HMM + Diff ── */}
      {hasResults && (
        <div className="space-y-5">

          {/* Self-corrected output */}
          {result.corrected_text && (
            <div className="card border-emerald-900/50">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-emerald-400 font-semibold text-sm">✨ Auto-Corrected Response</span>
                  <span className="text-xs text-gray-600 bg-gray-800 px-2 py-0.5 rounded">Self-Correction Loop</span>
                </div>
                <button
                  className="copy-btn text-xs"
                  onClick={() => { navigator.clipboard.writeText(result.corrected_text); toast.success('Copied') }}
                >
                  Copy
                </button>
              </div>
              <pre className="whitespace-pre-wrap text-sm text-gray-200 font-sans leading-relaxed bg-gray-950/60 rounded-xl p-4 max-h-96 overflow-y-auto">
                {result.corrected_text}
              </pre>
              <p className="text-xs text-gray-700 mt-2">
                The pipeline silently corrected hallucinations using authoritative knowledge-base evidence.
              </p>
            </div>
          )}

          {/* Before / After comparison */}
          {result.corrected_text && result.original_text &&
           result.corrected_text.trim() !== result.original_text.trim() && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-300 mb-3">Before / After Comparison</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-red-400 font-semibold mb-2">Original (with hallucinations)</p>
                  <pre className="whitespace-pre-wrap text-xs text-gray-500 font-sans leading-relaxed bg-red-950/20 border border-red-900/30 rounded-xl p-3 max-h-56 overflow-y-auto">
                    {result.original_text}
                  </pre>
                </div>
                <div>
                  <p className="text-xs text-emerald-400 font-semibold mb-2">Corrected (verified facts)</p>
                  <pre className="whitespace-pre-wrap text-xs text-gray-200 font-sans leading-relaxed bg-emerald-950/20 border border-emerald-900/30 rounded-xl p-3 max-h-56 overflow-y-auto">
                    {result.corrected_text}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* HMM Cascade visualization */}
          {result.claims?.length > 0 && (
            <CascadePoint
              claims={result.claims.map(c => ({ id: c.id, text: c.text, confidence: c.confidence }))}
              hmmStates={result.hmm_states || []}
              cascadePoint={result.cascade_point ?? null}
            />
          )}

          {/* FactualDiff + RARL reward breakdown */}
          {result.original_text && (
            <FactualDiff
              originalText={result.original_text}
              correctedText={result.corrected_text}
              rewardBreakdown={result.reward_breakdown}
              claims={result.claims?.map(c => ({ text: c.text })) || []}
            />
          )}
        </div>
      )}
    </div>
  )
}
