import { Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import Playground from './components/Playground'
import Dashboard from './components/Dashboard'
import KnowledgeBase from './components/KnowledgeBase'
import AuditLog from './components/AuditLog'
import Settings from './components/Settings'
import PerformanceGraph from './components/PerformanceGraph'
import { ToastProvider } from './components/Toast'

export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen flex flex-col page-bg">
        <Navbar />
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6 page-enter">
          <Routes>
            <Route path="/" element={<Navigate to="/playground" replace />} />
            <Route path="/playground" element={<Playground />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/performance" element={<PerformanceGraph />} />
            <Route path="/knowledge-base" element={<KnowledgeBase />} />
            <Route path="/audit" element={<AuditLog />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/playground" replace />} />
          </Routes>
        </main>
      </div>
    </ToastProvider>
  )
}
