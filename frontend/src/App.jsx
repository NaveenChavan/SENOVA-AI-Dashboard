import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import AppRoutes from './routes/AppRoutes'
import { auth, onAuthStateChanged, signOut } from './services/firebase'
import DensityToggle from './components/common/DensityToggle'
import ThemeToggle from './components/common/ThemeToggle'

/**
 * App shell: a single compact 52px header bar, the routed page, and a thin
 * footer. Everything sizes off the design tokens in index.css, so the shell
 * height never changes between breakpoints — which is what keeps the first
 * screen of the dashboard visible without scrolling.
 */
export default function App() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState(auth.currentUser)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, setUser)
    return unsubscribe
  }, [])

  // Close the account menu on an outside click or Escape — a popover that only
  // closes by clicking its own trigger traps keyboard users.
  useEffect(() => {
    if (!menuOpen) return undefined
    const onPointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) setMenuOpen(false)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [menuOpen])

  const navLinks = [
    { to: '/upload', label: 'Upload' },
    { to: '/dashboard', label: 'Dashboard' },
  ]

  const handleSignOut = async () => {
    setMenuOpen(false)
    await signOut()
    navigate('/login')
  }

  const initials = (user?.displayName || user?.email || '?').trim().charAt(0).toUpperCase()

  return (
    <div className="flex flex-col min-h-dvh">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>

      <header
        className="sticky top-0 z-40"
        style={{
          background: 'var(--bg-header)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <div className="app-container px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3" style={{ height: 52 }}>
          <Link to={user ? '/upload' : '/login'} className="flex items-center gap-2 shrink-0">
            <img
              src="/assets/logo.jpeg"
              alt="SENOVA"
              width={28}
              height={28}
              className="w-7 h-7 rounded-lg object-cover"
            />
            <span className="text-sm font-bold leading-none" style={{ color: 'var(--accent-blue)' }}>
              SENOVA
              <span className="font-light hidden sm:inline" style={{ color: 'var(--text-primary)' }}>
                {' '}Digital Lab
              </span>
            </span>
          </Link>

          <div className="flex items-center gap-2">
            {user && (
              <nav className="seg" aria-label="Main navigation">
                {navLinks.map(({ to, label }) => (
                  <Link
                    key={to}
                    to={to}
                    className="seg__btn"
                    // aria-current is the semantic "you are here"; the visual
                    // state reuses the same segmented-control styling.
                    aria-current={pathname.startsWith(to) ? 'page' : undefined}
                    aria-selected={pathname.startsWith(to)}
                    role="link"
                  >
                    {label}
                  </Link>
                ))}
              </nav>
            )}

            <DensityToggle />
            <ThemeToggle />

            {user && (
              <div className="relative" ref={menuRef}>
                <button
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  aria-label="Account menu"
                  className="rounded-full flex items-center justify-center text-xs font-bold cursor-pointer"
                  style={{
                    width: 28,
                    height: 28,
                    background: 'var(--accent-blue)',
                    color: 'var(--text-on-accent)',
                  }}
                >
                  {initials}
                </button>

                {menuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-52 rounded-xl overflow-hidden"
                    style={{
                      background: 'var(--bg-card-solid)',
                      border: '1px solid var(--border-subtle)',
                      boxShadow: 'var(--shadow-high)',
                    }}
                  >
                    <div className="px-3 py-2.5" style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <p className="text-xs font-semibold truncate" style={{ color: 'var(--text-primary)' }}>
                        {user.displayName || 'Signed in'}
                      </p>
                      <p className="text-[12px] truncate" style={{ color: 'var(--text-muted)' }}>
                        {user.email}
                      </p>
                    </div>
                    <button
                      role="menuitem"
                      onClick={handleSignOut}
                      className="w-full text-left px-3 py-2.5 text-xs font-medium cursor-pointer"
                      style={{ color: 'var(--accent-red)' }}
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

      <main id="main" className="flex-1 app-container w-full px-3 sm:px-5 lg:px-6 py-4 sm:py-5">
        <AppRoutes />
      </main>

      <footer
        className="text-center py-3 text-[12px]"
        style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}
      >
        SENOVA Digital Lab &mdash; Enterprise Preview
      </footer>
    </div>
  )
}
