import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, AreaChart, Area, BarChart, Bar, Legend,
} from 'recharts'
import { getAuditRecent } from '../api'

const TTD_TARGET = 1.5

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      {label != null && <div className="text-gray-400 mb-1">Request #{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || '#e5e7eb' }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toFixed(2) : p.value}</strong>
        </div>
      ))}
    </div>
  )
}

function KPI({ label, value, color = 'text-sky-300', sub }) {
  return (
    <div className="kpi-card">
      <div className={`kpi-value ${color}`}>{value}</div>
      <div className="kpi-label">{label}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function PerformanceGraph() {
  const [recent, setRecent] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const data = await getAuditRecent(50)
      setRecent(Array.isArray(data) ? data : [])
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [load])

  // Derive chart data
  const chartData = [...recent].reverse().slice(-30).map((r, i) => ({
    i: i + 1,
    ttd: r.ttd ?? null,
    reliability: r.reliability_score != null ? +(r.reliability_score * 100).toFixed(1) : null,
    reward: r.reward_score != null ? +r.reward_score.toFixed(3) : null,
    cascade: r.has_cascade ? 1 : 0,
    processing_ms: r.processing_time_ms ? Math.round(r.processing_time_ms) : null,
    claims: r.total_claims ?? 0,
  }))

  const withTTD = chartData.filter(d => d.ttd !== null)
  const avgTTD = withTTD.length
    ? (withTTD.reduce((s, d) => s + d.ttd, 0) / withTTD.length).toFixed(2)
    : '—'

  const cascadeCount = chartData.filter(d => d.cascade).length
  const avgReliability = chartData.filter(d => d.reliability !== null).length
    ? (chartData.filter(d => d.reliability !== null)
        .reduce((s, d) => s + d.reliability, 0) /
       chartData.filter(d => d.reliability !== null).length).toFixed(1)
    : '—'

  const avgReward = chartData.filter(d => d.reward !== null).length
    ? (chartData.filter(d => d.reward !== null)
        .reduce((s, d) => s + d.reward, 0) /
       chartData.filter(d => d.reward !== null).length).toFixed(3)
    : '—'

  const ttdMet = withTTD.filter(d => d.ttd <= TTD_TARGET).length
  const ttdPct = withTTD.length ? Math.round((ttdMet / withTTD.length) * 100) : 0

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Performance Metrics</h1>
        <div className="card text-gray-400 text-sm">Loading…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Performance Metrics</h1>
        <div className="card border-red-800 bg-red-950/40 text-red-300 text-sm">
          {error} <button onClick={load} className="ml-3 btn-secondary text-xs py-1">Retry</button>
        </div>
      </div>
    )
  }

  if (recent.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">Performance Metrics</h1>
          <button onClick={load} className="btn-secondary text-xs py-1.5">Refresh</button>
        </div>
        <div className="card border-gray-800 py-16 text-center space-y-4">
          <div className="text-6xl">📊</div>
          <h3 className="text-lg font-semibold text-gray-300">No performance data yet</h3>
          <p className="text-gray-500 text-sm max-w-md mx-auto leading-relaxed">
            Run a hallucination check in the <strong className="text-gray-300">Playground</strong> tab first.
            HMM reliability, Time-to-Detection, and RARL reward scores will appear here automatically.
          </p>
          <a href="/" className="btn-secondary text-sm inline-block mt-2">Go to Playground →</a>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Performance Metrics</h1>
          <p className="text-gray-500 text-sm mt-0.5">
            HMM reliability · Time-to-Detection · Reward system · Last {chartData.length} requests
          </p>
        </div>
        <button onClick={load} className="btn-secondary text-xs py-1.5">Refresh</button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <KPI
          label="Avg TTD"
          value={avgTTD === '—' ? '—' : `${avgTTD} claims`}
          color={avgTTD !== '—' && +avgTTD <= TTD_TARGET ? 'text-emerald-400' : 'text-yellow-400'}
          sub={`Target: ≤${TTD_TARGET} claims`}
        />
        <KPI
          label="TTD Target Met"
          value={withTTD.length ? `${ttdPct}%` : '—'}
          color={ttdPct >= 80 ? 'text-emerald-400' : 'text-yellow-400'}
          sub={`${ttdMet}/${withTTD.length} cascades`}
        />
        <KPI
          label="Avg Reliability"
          value={avgReliability === '—' ? '—' : `${avgReliability}%`}
          color={+avgReliability >= 80 ? 'text-emerald-400' : 'text-red-400'}
          sub="HMM Reliable states"
        />
        <KPI
          label="Avg Reward"
          value={avgReward}
          color={+avgReward >= 0 ? 'text-emerald-400' : 'text-red-400'}
          sub="RARL power-law score"
        />
      </div>

      {/* TTD Chart */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-1">
          Time-to-Detection (TTD) — claims before cascade caught
        </h3>
        <p className="text-xs text-gray-500 mb-3">
          Lower = better. Target &lt;{TTD_TARGET} sentences (red line).
        </p>
        {chartData.length === 0 ? (
          <div className="h-44 flex items-center justify-center text-gray-600 text-sm">
            No cascade data yet — verify some text first
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip content={<ChartTooltip />} />
              <ReferenceLine
                y={TTD_TARGET}
                stroke="#f87171"
                strokeDasharray="6 3"
                label={{ value: 'Target', fill: '#f87171', fontSize: 10, position: 'right' }}
              />
              <Line
                type="monotone"
                dataKey="ttd"
                name="TTD (claims)"
                stroke="#38bdf8"
                strokeWidth={2}
                dot={{ r: 3, fill: '#38bdf8' }}
                connectNulls={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Reliability + Reward side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* HMM Reliability */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            HMM Reliability Score (last 30)
          </h3>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="reliGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#34d399" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#34d399" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis domain={[0, 100]} tick={{ fill: '#6b7280', fontSize: 10 }} unit="%" />
              <Tooltip content={<ChartTooltip />} />
              <ReferenceLine y={80} stroke="#fbbf24" strokeDasharray="4 2" />
              <Area
                type="monotone"
                dataKey="reliability"
                name="Reliability"
                stroke="#34d399"
                strokeWidth={2}
                fill="url(#reliGrad)"
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Reward scores */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-300 mb-1">
            RARL Reward Score (last 30)
          </h3>
          <p className="text-xs text-gray-500 mb-2">
            J = -(α·log(q) − β·q² + r₀) · Higher = better. Negative = hallucination penalty.
          </p>
          <ResponsiveContainer width="100%" height={144}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
              <Tooltip content={<ChartTooltip />} />
              <ReferenceLine y={0} stroke="#6b7280" />
              <Bar
                dataKey="reward"
                name="Reward"
                fill="#a855f7"
                radius={[2, 2, 0, 0]}
                label={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

      </div>

      {/* Cascade events */}
      <div className="card">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">
          Cascade Events vs Total Claims (last 30 requests)
        </h3>
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="i" tick={{ fill: '#6b7280', fontSize: 10 }} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="claims" name="Claims" fill="#38bdf8" radius={[2, 2, 0, 0]} />
            <Bar dataKey="cascade" name="Cascade" fill="#f87171" radius={[2, 2, 0, 0]} />
            <Legend formatter={(v) => <span className="text-xs text-gray-300">{v}</span>} iconSize={10} />
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-gray-500 mt-2">
          Total cascades detected: <strong className="text-red-400">{cascadeCount}</strong> / {chartData.length} requests
        </p>
      </div>
    </div>
  )
}
