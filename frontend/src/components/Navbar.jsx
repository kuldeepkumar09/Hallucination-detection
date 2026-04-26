import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { getHealth } from '../api'

const NAV_LINKS = [
  { to: '/playground',     label: 'Playground'     },
  { to: '/dashboard',      label: 'Dashboard'      },
  { to: '/performance',    label: 'Performance'    },
  { to: '/knowledge-base', label: 'Knowledge Base' },
  { to: '/audit',          label: 'Audit Log'      },
  { to: '/settings',       label: 'Settings'       },
]

export default function Navbar() {
  const [status, setStatus]   = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)

  const checkHealth = useCallback(() => {
    getHealth()
      .then(d => setStatus({
        ok:         true,
        chunks:     d.knowledge_base?.total_chunks ?? '?',
        collection: d.knowledge_base?.collection ?? '',
        provider:   d.llm?.provider ?? '',
      }))
      .catch(() => setStatus({ ok: false }))
  }, [])

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 15000)
    return () => clearInterval(id)
  }, [checkHealth])

  const dotClass =
    status === null  ? 'status-dot status-dot-connecting' :
    status.ok        ? 'status-dot status-dot-online'     :
                       'status-dot status-dot-offline'

  const statusLabel =
    status === null  ? 'Connecting…'                              :
    status.ok        ? `${status.chunks} chunks · Online`         :
                       'Backend offline'

  return (
    <nav className="sticky top-0 z-30 border-b border-gray-800/80"
         style={{ background: 'rgba(3,7,18,0.85)', backdropFilter: 'blur(20px)' }}>
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">

        {/* Logo */}
        <NavLink to="/playground" className="flex items-center gap-2 mr-2 flex-shrink-0 group">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #0ea5e9, #6366f1, #34d399)' }}>
            <span className="text-white font-bold text-sm leading-none">H</span>
          </div>
          <span className="text-base font-bold gradient-text">HalluCheck</span>
          <span className="hidden sm:block text-xs text-gray-700 font-medium tracking-widest">v4</span>
        </NavLink>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-0.5 flex-1">
          {NAV_LINKS.map(l => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-900/40 text-sky-300 border border-sky-800/50'
                    : 'text-gray-500 hover:text-gray-200 hover:bg-gray-800/60'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </div>

        {/* Status indicator */}
        <div className="hidden sm:flex items-center gap-2 ml-auto text-xs flex-shrink-0">
          <span className={dotClass} />
          <span className="text-gray-600">{statusLabel}</span>
          {status?.ok && status?.provider && (
            <span className="text-gray-700 font-mono bg-gray-900 border border-gray-800 px-2 py-0.5 rounded text-xs">
              {status.provider}
            </span>
          )}
        </div>

        {/* Mobile menu toggle */}
        <button
          className="md:hidden ml-auto btn-secondary px-2 py-1.5 text-xs"
          onClick={() => setMenuOpen(v => !v)}
          aria-label="Toggle menu"
        >
          {menuOpen ? '✕' : '≡'}
        </button>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden border-t border-gray-800/60 px-4 py-3 flex flex-col gap-1"
             style={{ background: 'rgba(3,7,18,0.95)' }}>
          {NAV_LINKS.map(l => (
            <NavLink
              key={l.to}
              to={l.to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-900/40 text-sky-300'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-600">
            <span className={dotClass} />
            {statusLabel}
          </div>
        </div>
      )}
    </nav>
  )
}
