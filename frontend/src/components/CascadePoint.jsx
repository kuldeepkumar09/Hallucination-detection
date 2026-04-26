/**
 * CascadePoint — visual indicator of HMM trust breach location.
 * Shows the sequence of claim states (Reliable / Hallucinating) and
 * highlights the exact claim where the cascade began.
 */
export default function CascadePoint({ claims = [], hmmStates = [], cascadePoint = null }) {
  if (!claims.length) return null

  const hasCascade = cascadePoint !== null && cascadePoint >= 0

  return (
    <div className="card space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-300">HMM Reliability Sequence</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Hidden Markov Model — Viterbi decoded trust states per claim
          </p>
        </div>
        {hasCascade ? (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-red-900/60 text-red-300 border border-red-700">
            Cascade at claim #{cascadePoint + 1}
          </span>
        ) : (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700">
            No cascade detected
          </span>
        )}
      </div>

      {/* State timeline */}
      <div className="flex flex-wrap gap-2">
        {claims.map((claim, i) => {
          const state = hmmStates[i]
          const isCascadeStart = i === cascadePoint
          const isHallucinating = state === 1
          const isReliable = state === 0

          return (
            <div
              key={claim.id || i}
              className={`
                relative flex flex-col items-center gap-1 px-3 py-2 rounded-lg border text-xs
                transition-all duration-200
                ${isCascadeStart
                  ? 'border-red-500 bg-red-950/60 ring-2 ring-red-500 ring-offset-1 ring-offset-gray-900'
                  : isHallucinating
                    ? 'border-orange-700 bg-orange-950/40'
                    : 'border-emerald-800 bg-emerald-950/30'
                }
              `}
              style={{ minWidth: 80, maxWidth: 140 }}
            >
              {/* Cascade arrow */}
              {isCascadeStart && (
                <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-red-400 text-base">
                  ▼
                </div>
              )}

              {/* Claim index */}
              <span className="text-gray-500 font-mono text-[10px]">#{i + 1}</span>

              {/* State badge */}
              <span className={`font-semibold ${isHallucinating ? 'text-orange-400' : 'text-emerald-400'}`}>
                {isHallucinating ? 'Hallucinating' : 'Reliable'}
              </span>

              {/* Confidence */}
              <span className="text-gray-400 font-mono">
                {claim.confidence != null ? `q=${claim.confidence.toFixed(2)}` : '—'}
              </span>

              {/* Claim text snippet */}
              <span
                className="text-gray-500 text-center leading-tight"
                style={{ fontSize: 9, maxWidth: 130 }}
                title={claim.text}
              >
                {(claim.text || '').slice(0, 40)}{(claim.text || '').length > 40 ? '…' : ''}
              </span>
            </div>
          )
        })}
      </div>

      {/* Transition arrows between states */}
      {hmmStates.length > 1 && (
        <div className="flex items-center gap-1 flex-wrap text-xs text-gray-600">
          {hmmStates.map((state, i) => {
            if (i === hmmStates.length - 1) return null
            const next = hmmStates[i + 1]
            const isTransition = state !== next
            return (
              <span key={i} className={isTransition ? 'text-red-500 font-bold' : 'text-gray-700'}>
                {isTransition ? '→⚠' : '→'}
              </span>
            )
          })}
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500 pt-1 border-t border-gray-800">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-emerald-900 border border-emerald-700 inline-block" />
          Reliable (HMM state 0)
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-orange-900 border border-orange-700 inline-block" />
          Hallucinating (HMM state 1)
        </span>
        {hasCascade && (
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm bg-red-900 border border-red-500 ring-1 ring-red-500 inline-block" />
            Cascade start
          </span>
        )}
      </div>
    </div>
  )
}
