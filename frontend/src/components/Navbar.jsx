import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { getHealth } from '../api'

const NAV_LINKS = [
  { to: '/playground',     label: 'Playground' },
  { to: '/dashboard',      label: 'Dashboard' },
  { to: '/knowledge-base', label: 'Knowledge Base' },
  { to: '/audit',          label: 'Audit Log' },
  { to: '/settings',       label: 'Settings' },
]

export default function Navbar() {
  const [status, setStatus] = useState(null)   // null=loading, {ok,chunks,collection}
  const [menuOpen, setMenuOpen] = useState(false)

  const checkHealth = useCallback(() => {
    getHealth()
      .then((d) =>
        setStatus({
          ok: true,
          chunks: d.knowledge_base?.total_chunks ?? '?',
          collection: d.knowledge_base?.collection ?? '',
        })
      )
      .catch(() => setStatus({ ok: false }))
  }, [])

  useEffect(() => {
    checkHealth()
    const id = setInterval(checkHealth, 15000)
    return () => clearInterval(id)
  }, [checkHealth])

  const dotClass =
    status === null
      ? 'status-dot status-dot-connecting'
      : status.ok
      ? 'status-dot status-dot-online'
      : 'status-dot status-dot-offline'

  const statusLabel =
    status === null
      ? 'Connecting…'
      : status.ok
      ? `${status.chunks} chunks · Online`
      : 'Backend offline'

  return (
    <nav className="bg-gray-900/80 backdrop-blur border-b border-gray-800 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-4">
        {/* Logo */}
        <NavLink to="/playground" className="flex items-center gap-2 mr-2 flex-shrink-0">
          <span className="text-base font-bold bg-gradient-to-r from-sky-400 to-violet-400 bg-clip-text text-transparent">
            HalluCheck
          </span>
          <span className="hidden sm:block text-xs text-gray-600 font-medium tracking-wide">v2.1</span>
        </NavLink>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-1 flex-1">
          {NAV_LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-900/50 text-sky-300'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
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
          <span className="text-gray-500">{statusLabel}</span>
        </div>

        {/* Mobile menu toggle */}
        <button
          className="md:hidden ml-auto btn-secondary px-2 py-1.5 text-xs"
          onClick={() => setMenuOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {menuOpen ? 'X' : '='}
        </button>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden border-t border-gray-800 bg-gray-900 px-4 py-3 flex flex-col gap-1">
          {NAV_LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) =>
                `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-sky-900/50 text-sky-300'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-500">
            <span className={dotClass} />
            {statusLabel}
          </div>
        </div>
      )}
    </nav>
  )
}
