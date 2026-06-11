import { Link, useLocation } from 'react-router-dom'
import AppRoutes from './routes/AppRoutes'

export default function App() {
  const { pathname } = useLocation()

  const navLinks = [
    { to: '/upload', label: 'Upload' },
    { to: '/dashboard', label: 'Dashboard' },
  ]

  return (
    <div className="flex flex-col min-h-screen">
      <header style={{
        background: 'rgba(5, 13, 26, 0.9)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border-subtle)',
        position: 'sticky', top: 0, zIndex: 50
      }}>
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link to="/upload" className="flex items-center gap-3">
            <div style={{
              width: 36, height: 36,
              background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
              borderRadius: 10,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 16px rgba(56,189,248,0.3)'
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5">
                <path d="M13 10V3L4 14h7v7l9-11h-7z"/>
              </svg>
            </div>
            <div>
              <span className="text-lg font-bold glow-blue-text" style={{color:'var(--accent-blue)'}}>SENOVA</span>
              <span className="text-lg font-light" style={{color:'var(--text-primary)'}}> Digital Lab</span>
            </div>
          </Link>

          <nav className="flex gap-1">
            {navLinks.map(({ to, label }) => (
              <Link key={to} to={to} style={{
                padding: '8px 16px',
                borderRadius: 8,
                fontSize: '0.875rem',
                fontWeight: 500,
                transition: 'all 0.2s',
                color: pathname.startsWith(to) ? 'var(--accent-blue)' : 'var(--text-secondary)',
                background: pathname.startsWith(to) ? 'rgba(56,189,248,0.08)' : 'transparent',
                border: pathname.startsWith(to) ? '1px solid var(--border-subtle)' : '1px solid transparent',
              }}>
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 sm:py-8">
        <AppRoutes />
      </main>

      <footer className="text-center text-xs py-4 border-t" style={{color:'var(--text-muted)', borderColor:'var(--border-subtle)'}}>
        SENOVA Digital Lab &mdash; Enterprise Preview
      </footer>
    </div>
  )
}
