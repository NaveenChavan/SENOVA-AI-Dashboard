import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import AppRoutes from './routes/AppRoutes'
import { auth, onAuthStateChanged, signOut } from './services/firebase'
import ThemeToggle from './components/common/ThemeToggle'

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
      <header
        style={{
          background: 'var(--bg-header)',
          backdropFilter: 'blur(16px)',
          borderBottom: '1px solid var(--border-subtle)',
          position: 'sticky',
          top: 0,
          zIndex: 50,
        }}
      >
        <div className="app-container px-4 sm:px-6 lg:px-8 py-3 sm:py-4 flex items-center justify-between">
          <Link to={user ? '/upload' : '/login'} className="flex items-center gap-2.5 sm:gap-3 shrink-0">
            <img
              src="/assets/logo.jpeg"
              alt="SENOVA"
              width={36}
              height={36}
              className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl object-cover"
              style={{ boxShadow: '0 0 16px var(--accent-blue-glow)' }}
            />
            <div className="leading-tight">
              <span className="text-base sm:text-lg font-bold glow-blue-text" style={{ color: 'var(--accent-blue)' }}>
                SENOVA
              </span>
              <span className="text-base sm:text-lg font-light hidden sm:inline" style={{ color: 'var(--text-primary)' }}>
                {' '}Digital Lab
              </span>
            </div>
          </Link>

          <div className="flex items-center gap-1.5 sm:gap-3 lg:gap-4">
            {user && (
              <nav className="flex gap-1">
                {navLinks.map(({ to, label }) => (
                  <Link
                    key={to}
                    to={to}
                    className="text-xs sm:text-sm"
                    style={{
                      padding: '10px 10px',
                      minHeight: 40,
                      display: 'inline-flex',
                      alignItems: 'center',
                      borderRadius: 8,
                      fontWeight: 500,
                      color: pathname.startsWith(to) ? 'var(--accent-blue)' : 'var(--text-secondary)',
                      background: pathname.startsWith(to) ? 'var(--accent-blue-glow)' : 'transparent',
                      border: pathname.startsWith(to) ? '1px solid var(--border-subtle)' : '1px solid transparent',
                    }}
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            )}

            <ThemeToggle />

            {user && (
              <div className="relative">
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-haspopup="true"
                  aria-expanded={menuOpen}
                  aria-label="Account menu"
                  className="w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center text-xs sm:text-sm font-semibold transition-transform hover:scale-105"
                  style={{
                    background: 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))',
                    color: 'var(--text-on-accent)',
                  }}
                >
                  {initials}
                </button>

                {menuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-56 rounded-xl overflow-hidden"
                    style={{
                      background: 'var(--bg-card-solid)',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-elevation-high)',
                    }}
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
                      className="w-full text-left px-4 py-3 text-sm transition-colors"
                      style={{ color: 'var(--accent-red)' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(239,68,68,0.08)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
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

      <main className="flex-1 app-container w-full px-4 sm:px-6 lg:px-8 py-5 sm:py-8">
        <AppRoutes />
      </main>

      <footer
        className="text-center text-xs py-4 border-t"
        style={{ color: 'var(--text-muted)', borderColor: 'var(--border-subtle)' }}
      >
        SENOVA Digital Lab &mdash; Enterprise Preview
      </footer>
    </div>
  )
}
