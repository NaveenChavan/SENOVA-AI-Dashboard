import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import AppRoutes from './routes/AppRoutes'
import { auth, onAuthStateChanged, signOut } from './services/firebase'

export default function App() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState(auth.currentUser)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, setUser)
    return unsubscribe
  }, [])

  const navLinks = [
    { to: '/upload', label: 'Upload' },
    { to: '/dashboard', label: 'Dashboard' },
  ]

  const handleSignOut = async () => {
    setMenuOpen(false)
    await signOut()
    navigate('/login')
  }

  const initials = (user?.displayName || user?.email || '?')
    .trim()
    .charAt(0)
    .toUpperCase()

  return (
    <div className="flex flex-col min-h-screen">
      <header style={{
        background: 'rgba(5, 13, 26, 0.9)',
        backdropFilter: 'blur(16px)',
        borderBottom: '1px solid var(--border-subtle)',
        position: 'sticky', top: 0, zIndex: 50
      }}>
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <Link to={user ? '/upload' : '/login'} className="flex items-center gap-3">
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
              <span className="text-lg font-light hidden sm:inline" style={{color:'var(--text-primary)'}}> Digital Lab</span>
            </div>
          </Link>

          <div className="flex items-center gap-2 sm:gap-4">
            {user && (
              <nav className="flex gap-1">
                {navLinks.map(({ to, label }) => (
                  <Link key={to} to={to} style={{
                    padding: '8px 12px',
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
            )}

            {user && (
              <div className="relative">
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-haspopup="true"
                  aria-expanded={menuOpen}
                  aria-label="Account menu"
                  className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-transform hover:scale-105"
                  style={{
                    background: 'linear-gradient(135deg, #0ea5e9, #38bdf8)',
                    color: '#fff',
                  }}
                >
                  {initials}
                </button>

                {menuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 rounded-xl overflow-hidden shadow-xl"
                    style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}
                  >
                    <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
                      <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
                        {user.displayName || 'Signed in'}
                      </p>
                      <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>
                        {user.email}
                      </p>
                    </div>
                    <button
                      role="menuitem"
                      onClick={handleSignOut}
                      className="w-full text-left px-4 py-3 text-sm hover:bg-red-500/10 transition-colors"
                      style={{ color: '#f87171' }}
                    >
                      Sign out
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 py-6 sm:py-8">
        <AppRoutes />
      </main>

      <footer className="text-center text-xs py-4 border-t" style={{color:'var(--text-muted)', borderColor:'var(--border-subtle)'}}>
        SENOVA Digital Lab &mdash; Enterprise Preview
      </footer>
    </div>
  )
}
