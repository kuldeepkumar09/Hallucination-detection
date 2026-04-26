/**
 * FactualDiff — side-by-side original vs corrected text with reward scores.
 * Shows per-claim reward/cost breakdown alongside the text diff.
 */
export default function FactualDiff({ originalText, correctedText, rewardBreakdown, claims = [] }) {
  if (!originalText) return null

  const hasCorrection = correctedText && correctedText !== originalText
  const hasCost = rewardBreakdown?.per_claim?.length > 0

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-sm font-semibold text-gray-300">Factual Diff — Original vs Corrected</h3>
        {rewardBreakdown && (
          <div className="flex items-center gap-3 text-xs">
            <span className="text-gray-500">
              Total reward:
              <span className={`ml-1 font-mono font-semibold ${rewardBreakdown.total_reward >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {rewardBreakdown.total_reward?.toFixed(4)}
              </span>
            </span>
            <span className="text-gray-500">
              Avg reward:
              <span className={`ml-1 font-mono font-semibold ${rewardBreakdown.avg_reward >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {rewardBreakdown.avg_reward?.toFixed(4)}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Text side-by-side */}
      <div className={`grid gap-4 ${hasCorrection ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'}`}>
        {/* Original */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Original</span>
            <span className="h-px flex-1 bg-gray-800" />
          </div>
          <div className="bg-gray-900 rounded-lg p-3 text-sm text-gray-300 leading-relaxed border border-gray-800 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto">
            {originalText}
          </div>
        </div>

        {/* Corrected */}
        {hasCorrection && (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-emerald-500 uppercase tracking-wider">Corrected</span>
              <span className="h-px flex-1 bg-gray-800" />
            </div>
            <div className="bg-gray-900 rounded-lg p-3 text-sm text-emerald-300 leading-relaxed border border-emerald-900 font-mono whitespace-pre-wrap max-h-64 overflow-y-auto">
              {correctedText}
            </div>
          </div>
        )}

        {!hasCorrection && (
          <div className="text-xs text-gray-600 italic pt-1">
            No correction applied — all claims passed or self-correction disabled.
          </div>
        )}
      </div>

      {/* Per-claim reward breakdown */}
      {hasCost && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            RARL Cost Function — J = -(α·log(q) − β·q² + r₀) per claim
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-500 border-b border-gray-800">
                  <th className="text-left py-1.5 pr-3">#</th>
                  <th className="text-left py-1.5 pr-3">Claim</th>
                  <th className="text-left py-1.5 pr-3">Status</th>
                  <th className="text-right py-1.5 pr-3">q (conf)</th>
                  <th className="text-right py-1.5 pr-3">Cost J</th>
                  <th className="text-right py-1.5">Reward</th>
                </tr>
              </thead>
              <tbody>
                {rewardBreakdown.per_claim.map((item, i) => {
                  const claim = claims[i]
                  const isPositive = item.reward >= 0
                  return (
                    <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="py-1.5 pr-3 text-gray-600 font-mono">{i + 1}</td>
                      <td className="py-1.5 pr-3 text-gray-300 max-w-xs truncate">
                        {claim?.text?.slice(0, 60) || '—'}
                      </td>
                      <td className="py-1.5 pr-3">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono text-gray-300">
                        {item.confidence.toFixed(3)}
                      </td>
                      <td className="py-1.5 pr-3 text-right font-mono text-orange-400">
                        {item.cost.toFixed(4)}
                      </td>
                      <td className={`py-1.5 text-right font-mono font-semibold ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                        {isPositive ? '+' : ''}{item.reward.toFixed(4)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-gray-700 text-gray-400 font-semibold">
                  <td colSpan={4} className="py-1.5 pr-3 text-right text-gray-500 text-xs">Total</td>
                  <td className="py-1.5 pr-3 text-right font-mono text-orange-400">
                    {rewardBreakdown.total_cost?.toFixed(4)}
                  </td>
                  <td className={`py-1.5 text-right font-mono ${rewardBreakdown.total_reward >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {rewardBreakdown.total_reward >= 0 ? '+' : ''}{rewardBreakdown.total_reward?.toFixed(4)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          <p className="text-[10px] text-gray-600">
            α={rewardBreakdown.alpha} · β={rewardBreakdown.beta} · γ={rewardBreakdown.gamma} · r₀={rewardBreakdown.r0}
          </p>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    verified: 'text-emerald-400 bg-emerald-950 border-emerald-800',
    contradicted: 'text-red-400 bg-red-950 border-red-800',
    partially_supported: 'text-yellow-400 bg-yellow-950 border-yellow-800',
    unverifiable: 'text-gray-400 bg-gray-800 border-gray-700',
  }
  const cls = map[status] || map.unverifiable
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${cls}`}>
      {status?.replace('_', ' ')}
    </span>
  )
}
