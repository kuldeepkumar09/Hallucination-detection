import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, BarChart, Bar, CartesianGrid,
  AreaChart, Area,
} from 'recharts'
import { getAuditStats, getAuditRecent, getKBStats, getCacheStats, getCategoryStats } from '../api'

const PIE_COLORS = {
  pass:     '#6b7280',
  annotate: '#38bdf8',
  flag:     '#fbbf24',
  block:    '#f87171',
}

const CONF_COLOR = (c) => {
  if (c >= 0.8) return '#34d399'
  if (c >= 0.5) return '#fbbf24'
  return '#f87171'
}

function ChartTooltip({ active, payload, label, unit = '' }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      {label != null && <div className="text-gray-400 mb-1">{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || p.fill || '#e5e7eb' }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toFixed(p.value < 1 ? 2 : 0) : p.value}{unit}</strong>
        </div>
      ))}
    </div>
  )
}

function KPICard({ label, value, color = 'text-sky-300', sub }) {
  return (
    <div className="kpi-card">
      <div className={`kpi-value ${color}`}>{value}</div>
      <div className="kpi-label">{label}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats]       = useState(null)
  const [recent, setRecent]     = useState([])
  const [kbStats, setKbStats]   = useState(null)
  const [cacheStats, setCache]  = useState(null)
  const [catStats, setCatStats] = useState({})
  const [error, setError]       = useState(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefreshed, setLastRefreshed] = useState(null)
  const [apiKey, setApiKey]     = useState(() => localStorage.getItem('api_key') || '')
  const [showApiKey, setShowApiKey] = useState(false)

  // Save API key to localStorage when changed
  const handleApiKeyChange = (value) => {
    setApiKey(value)
    localStorage.setItem('api_key', value)
  }

  const load = useCallback(async () => {
    try {
      const [s, r, kb, cs, cat] = await Promise.all([
        getAuditStats(),
        getAuditRecent(30),
        getKBStats(),
        getCacheStats(),
        getCategoryStats(),
      ])
      setStats(s)
      setRecent(Array.isArray(r) ? r : [])
      setKbStats(kb)
      setCache(cs)
      setCatStats(cat && typeof cat === 'object' ? cat : {})
      setError(null)
      setLastRefreshed(new Date())
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [autoRefresh, load])

  // ── Derived chart data ────────────────────────────────────────────

  const confidenceData = [...recent].reverse().slice(-20).map((r, i) => ({
    i: i + 1,
    confidence: r.overall_confidence != null ? +(r.overall_confidence * 100).toFixed(1) : null,
    model: r.model || '—',
  }))

  const processingData = [...recent].reverse().slice(-20).map((r, i) => ({
    i: i + 1,
    ms: r.processing_time_ms != null ? Math.round(r.processing_time_ms) : null,
  }))

  const actionData = stats
    ? [
        { name: 'PASS',     value: stats.total_pass     ?? 0, fill: PIE_COLORS.pass },
        { name: 'ANNOTATE', value: stats.total_annotate  ?? 0, fill: PIE_COLORS.annotate },
        { name: 'FLAG',     value: stats.total_flagged   ?? 0, fill: PIE_COLORS.flag },
        { name: 'BLOCK',    value: stats.total_blocked   ?? 0, fill: PIE_COLORS.block },
      ].filter((d) => d.value > 0)
    : []

  // Claim type breakdown from recent entries
  const typeMap = {}
  recent.forEach((r) => {
    if (!Array.isArray(r.claims)) return
    r.claims.forEach((c) => {
      const t = c.type || 'unknown'
      typeMap[t] = (typeMap[t] || 0) + 1
    })
  })
  const typeData = Object.entries(typeMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([name, count]) => ({ name, count }))

  // Per-request stacked bar (last 10)
  const stackedData = [...recent].reverse().slice(-10).map((r, i) => ({
    i: i + 1,
    verified: r.verified_count ?? 0,
    flagged:  r.flagged_count  ?? 0,
    blocked:  r.blocked_count  ?? 0,
  }))

  // Category breakdown chart data
  const categoryData = Object.entries(catStats).map(([name, d]) => ({
    name,
    verified: d.verified ?? 0,
    flagged:  d.flagged  ?? 0,
    blocked:  d.blocked  ?? 0,
  }))

  const blockRate = stats?.total_requests
    ? ((stats.blocked_responses / stats.total_requests) * 100).toFixed(1)
    : '0.0'

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <div className="card border-red-800 bg-red-950/40 text-red-300 text-sm space-y-2">
          <p className="font-semibold">Backend offline or unreachable</p>
          <p className="text-red-400/70">{error}</p>
          <button onClick={load} className="btn-secondary text-xs py-1">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            Live monitoring ·{' '}
            {lastRefreshed ? `Updated ${lastRefreshed.toLocaleTimeString()}` : 'Loading…'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={load} className="btn-secondary text-xs py-1.5">Refresh</button>
          <label className="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
            <input
              type="checkbox"
              className="accent-sky-500"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (10s)
          </label>
          <button
            onClick={() => setShowApiKey(!showApiKey)}
            className="btn-secondary text-xs py-1.5"
          >
            {showApiKey ? 'Hide API Key' : 'Settings'}
          </button>
        </div>
      </div>

      {/* API Key Settings */}
      {showApiKey && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">API Authentication</h3>
          <div className="flex items-center gap-3">
            <input
              type="password"
              value={apiKey}
              onChange={(e) => handleApiKeyChange(e.target.value)}
              placeholder="Enter API key (empty = no auth)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
            <span className="text-xs text-gray-500">
              {apiKey ? 'Auth enabled' : 'Auth disabled (dev mode)'}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            API key is stored in browser localStorage. Set in <code className="bg-gray-800 px-1 rounded">.env</code> on the server.
          </p>
        </div>
      )}

      {/* KPI Cards row — primary metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICard label="Total Requests"  value={stats?.total_requests ?? '—'}       color="text-sky-300" />
        <KPICard label="Total Claims"    value={stats?.total_claims ?? '—'}         color="text-violet-400" />
        <KPICard label="Avg Confidence"  value={stats ? `${(stats.avg_confidence * 100).toFixed(0)}%` : '—'} color="text-emerald-400" />
        <KPICard label="Block Rate"      value={`${blockRate}%`}                    color="text-red-400" />
        <KPICard label="Avg Time"        value={stats ? `${Math.round(stats.avg_processing_ms)}ms` : '—'} color="text-yellow-400" />
        <KPICard label="KB Chunks"       value={kbStats?.total_chunks ?? '—'}       color="text-sky-300" sub={kbStats?.bm25_enabled ? 'BM25 on' : 'BM25 off'} />
      </div>

      {/* KPI Cards row — action counters (live) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-3 gap-3">
        <KPICard
          label="Blocked Claims"
          value={stats?.total_blocked ?? '—'}
          color="text-red-400"
          sub={stats ? `${stats.blocked_responses ?? 0} blocked responses` : undefined}
        />
        <KPICard
          label="Flagged Claims"
          value={stats?.total_flagged ?? '—'}
          color="text-yellow-400"
          sub={stats ? `${stats.flagged_responses ?? 0} flagged responses` : undefined}
        />
        <KPICard
          label="Corrected Responses"
          value={stats?.corrected_count ?? '—'}
          color="text-green-400"
          sub="Self-correction loop"
        />
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Confidence trend */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Confidence Trend (last 20)</h3>
          {confidenceData.length === 0 ? (
            <div className="h-44 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={176}>
              <LineChart data={confidenceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 10 }} unit="%" />
                <Tooltip content={<ChartTooltip unit="%" />} />
                <Line
                  type="monotone"
                  dataKey="confidence"
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={{ r: 3, fill: '#a855f7' }}
                  activeDot={{ r: 5 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Action distribution donut */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Action Distribution</h3>
          {actionData.length === 0 ? (
            <div className="h-44 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={176}>
              <PieChart>
                <Pie
                  data={actionData}
                  cx="50%" cy="50%"
                  innerRadius={45} outerRadius={70}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {actionData.map((d, i) => <Cell key={i} fill={d.fill} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend
                  formatter={(v) => <span className="text-xs text-gray-300">{v}</span>}
                  iconSize={10}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Processing time area chart */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Processing Time (last 20)</h3>
          {processingData.length === 0 ? (
            <div className="h-44 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={176}>
              <AreaChart data={processingData}>
                <defs>
                  <linearGradient id="msGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#fbbf24" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#fbbf24" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} unit="ms" />
                <Tooltip content={<ChartTooltip unit="ms" />} />
                <Area
                  type="monotone"
                  dataKey="ms"
                  stroke="#fbbf24"
                  strokeWidth={2}
                  fill="url(#msGrad)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Claim type bar chart */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Claims by Type</h3>
          {typeData.length === 0 ? (
            <div className="h-44 flex items-center justify-center text-gray-600 text-sm">No data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={176}>
              <BarChart data={typeData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} />
                <YAxis type="category" dataKey="name" tick={{ fill: '#9ca3af', fontSize: 10 }} width={80} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" fill="#38bdf8" radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

      </div>

      {/* Stacked per-request bar */}
      {stackedData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Verified / Flagged / Blocked per Request (last 10)</h3>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={stackedData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="verified" stackId="a" fill="#34d399" name="Verified" />
              <Bar dataKey="flagged"  stackId="a" fill="#fbbf24" name="Flagged" />
              <Bar dataKey="blocked"  stackId="a" fill="#f87171" name="Blocked" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Category breakdown chart */}
      {categoryData.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Claims by Category (Verified / Flagged / Blocked)</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={categoryData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="verified" stackId="cat" fill="#34d399" name="Verified" />
              <Bar dataKey="flagged"  stackId="cat" fill="#fbbf24" name="Flagged" />
              <Bar dataKey="blocked"  stackId="cat" fill="#f87171" name="Blocked" radius={[3, 3, 0, 0]} />
              <Legend formatter={(v) => <span className="text-xs text-gray-300">{v}</span>} iconSize={10} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Cache stats */}
      {cacheStats && (
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Verification Cache</h3>
          <div className="flex flex-wrap gap-6 text-sm">
            <div>
              <span className="text-gray-500">Hit Rate</span>
              <span className="ml-2 font-mono text-emerald-400">
                {cacheStats.hit_rate != null ? `${(cacheStats.hit_rate * 100).toFixed(1)}%` : '—'}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Hits</span>
              <span className="ml-2 font-mono text-gray-200">{cacheStats.hits ?? '—'}</span>
            </div>
            <div>
              <span className="text-gray-500">Misses</span>
              <span className="ml-2 font-mono text-gray-200">{cacheStats.misses ?? '—'}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
