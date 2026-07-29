import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, useMotionValueEvent, useScroll } from 'motion/react'

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

  // The login screen owns its entire viewport (its own full-bleed hero +
  // sign-in layout) — wrapping it in the app shell's header/footer double-
  // chromes the page and pushes it past one viewport height, which is what
  // caused the header's Upload/Dashboard nav and account avatar to appear on
  // top of the sign-in screen even for a signed-out visitor.
  const isAuthScreen = pathname.startsWith('/login')

  // Auto-hiding header: slides up out of view on scroll-down, slides back in
  // on scroll-up (or once the user is back near the top). Both the header AND
  // the dashboard's sticky toolbar are driven off this *same* Motion value
  // (via a CSS variable kept in sync every scroll frame, not a React state
  // flip) — two independent systems animating "together" is what caused the
  // header and toolbar to visibly desync into two separate jumps.
  const { scrollY } = useScroll()
  const [headerHidden, setHeaderHidden] = useState(false)
  const lastScrollY = useRef(0)
  const mainRef = useRef(null)

  useMotionValueEvent(scrollY, 'change', (current) => {
    const previous = lastScrollY.current
    const scrollingDown = current > previous
    // Never hide while still near the top — the header snapping away in the
    // first few pixels of a scroll reads as broken, not smooth.
    const hidden = scrollingDown && current > 80
    setHeaderHidden(hidden)
    // Written directly to the DOM on every scroll-change event, in the same
    // tick as the header's own transform — no waiting for a React re-render,
    // which is what kept the toolbar a frame or more behind the header.
    if (mainRef.current) {
      mainRef.current.style.setProperty('--header-offset', hidden ? '0px' : '52px')
    }
    lastScrollY.current = current
  })

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

  if (isAuthScreen) {
    return (
      <>
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        <div id="main">
          <AppRoutes />
        </div>
      </>
    )
  }

  return (
    <div className="flex flex-col min-h-dvh">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>

      <motion.header
        className="sticky top-0 z-40"
        style={{
          background: 'var(--bg-header)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
        animate={{ y: headerHidden ? '-100%' : 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="app-container px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-3" style={{ height: 52 }}>
          <Link to={user ? '/upload' : '/login'} className="flex items-center gap-2.5 shrink-0">
            <span
              className="shrink-0 rounded-lg overflow-hidden"
              style={{ width: 30, height: 30, border: '1px solid var(--border-subtle)' }}
            >
              <img src="/assets/logo.jpeg" alt="SENOVA" width={30} height={30} className="w-full h-full object-cover" />
            </span>
            <span className="text-display text-sm font-bold leading-none tracking-tight" style={{ color: 'var(--text-primary)' }}>
              SENOVA
              <span className="hidden sm:block font-sans text-[9px] font-semibold tracking-[0.14em] uppercase mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Digital Lab
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
                    background: 'var(--gradient-accent)',
                    color: '#ffffff',
                    boxShadow: 'var(--shadow-glow)',
                  }}
                >
                  {initials}
                </button>

                <AnimatePresence>
                  {menuOpen && (
                    <motion.div
                      role="menu"
                      className="absolute right-0 mt-2 w-52 rounded-xl overflow-hidden"
                      initial={{ opacity: 0, y: -6, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -6, scale: 0.98 }}
                      transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
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
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>
      </motion.header>

      <main
        id="main"
        ref={mainRef}
        className="flex-1 app-container w-full px-3 sm:px-5 lg:px-6 py-4 sm:py-5"
        style={{ '--header-offset': '52px' }}
      >
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
