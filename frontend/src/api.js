const BASE = 'http://localhost:8080'

async function apiFetch(path, options = {}, timeoutMs = 30000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${BASE}${path}`, { ...options, signal: controller.signal })
    clearTimeout(timer)
    if (!res.ok) {
      let detail
      try { detail = (await res.json()).detail } catch { detail = res.statusText }
      throw new Error(detail || `HTTP ${res.status}`)
    }
    return res.json()
  } catch (e) {
    clearTimeout(timer)
    if (e.name === 'AbortError') throw new Error(`Request timed out after ${timeoutMs / 1000}s`)
    throw e
  }
}

export const verifyText = (text, model = 'playground') =>
  apiFetch('/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, model }),
  }, 600000)  // 10 min — Ollama can take 2-3 min on first run (model loading)

export const getHealth = () => apiFetch('/health', {}, 10000)

export const getAuditRecent = (n = 50) => apiFetch(`/audit/recent?n=${n}`)

export const getAuditStats = () => apiFetch('/audit/stats')

export const getKBStats = () => apiFetch('/kb/stats')

export const getKBDocuments = () => apiFetch('/kb/documents')

export const ingestText = (text, source) =>
  apiFetch('/kb/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source }),
  })

export const ingestUrl = (url, source) =>
  apiFetch('/kb/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, source }),
  }, 60000)

export const ingestWikipedia = (topic, language = 'en') =>
  apiFetch('/kb/ingest/wikipedia', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, language }),
  }, 60000)

export const deleteDocument = (doc_id) =>
  apiFetch(`/kb/documents/${encodeURIComponent(doc_id)}`, { method: 'DELETE' })

export const getCacheStats = () => apiFetch('/cache/stats')

export const clearCache = () =>
  apiFetch('/cache/clear', { method: 'POST' })
