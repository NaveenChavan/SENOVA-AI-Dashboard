import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, useMotionValueEvent, useScroll } from 'motion/react'

import AppRoutes from './routes/AppRoutes'
import { auth, onAuthStateChanged, signOut } from './services/firebase'
import { displayIdentifier } from './utils/authValidation'
import DensityToggle from './components/common/DensityToggle'
import ThemeToggle from './components/common/ThemeToggle'
import DeleteAccountDialog from './components/common/DeleteAccountDialog'

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
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const menuRef = useRef(null)

  // The auth screens (login, signup, forgot-password, verify-email) each own
  // their entire viewport (a full-bleed hero + centred card layout, with
  // their own logo mark) — wrapping any of them in the app shell's
  // header/footer double-chromes the page, duplicates the theme toggle, and
  // pushes the page past one viewport height.
  const isAuthScreen = ['/login', '/signup', '/forgot-password', '/verify-email'].some((p) => pathname.startsWith(p))

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
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser)
      // Account deletion signs the user out as a side effect — close the
      // confirmation dialog once that happens so it doesn't linger over
      // whatever the guard redirects to.
      if (!firebaseUser) setDeleteDialogOpen(false)
    })
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

  const initials = (user?.displayName || displayIdentifier(user) || '?').trim().charAt(0).toUpperCase()

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
        <div className="app-container px-3 sm:px-5 lg:px-6 flex items-center justify-between gap-2 sm:gap-3" style={{ height: 52 }}>
          <Link to={user ? '/upload' : '/login'} className="flex items-center gap-2.5 min-w-0 shrink">
            <span
              className="shrink-0 rounded-lg overflow-hidden"
              style={{ width: 30, height: 30, border: '1px solid var(--border-subtle)' }}
            >
              <img src="/assets/logo.jpeg" alt="SENOVA" width={30} height={30} className="w-full h-full object-cover" />
            </span>
            {/* Wordmark is hidden on phones: the logo tile beside it already
                carries the brand, and at 375px this text was ~72px of the
                overflow that dragged the whole header (and page) sideways.
                Nav labels are kept instead — they're primary navigation,
                whereas a second brand cue is redundant. */}
            <span className="hidden sm:block text-display text-sm font-bold leading-none tracking-tight min-w-0 truncate" style={{ color: 'var(--text-primary)' }}>
              SENOVA
              <span className="hidden sm:block font-sans text-[9px] font-semibold tracking-[0.14em] uppercase mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Digital Lab
              </span>
            </span>
          </Link>

          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            {user && (
              <nav className="seg min-w-0" aria-label="Main navigation">
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

            {/* Density is a comfort preference for dense desktop tables; on a
                phone the tables scroll regardless, so it's the least-essential
                control here and the first to go when width is scarce. */}
            <span className="hidden sm:inline-flex shrink-0">
              <DensityToggle />
            </span>
            <span className="shrink-0">
              <ThemeToggle />
            </span>

            {user && (
              <div className="relative shrink-0" ref={menuRef}>
                <button
                  onClick={() => setMenuOpen((open) => !open)}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  aria-label="Account menu"
                  className="rounded-full flex items-center justify-center text-xs font-bold cursor-pointer shrink-0"
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
                          {displayIdentifier(user)}
                        </p>
                      </div>
                      <button
                        role="menuitem"
                        onClick={handleSignOut}
                        className="w-full text-left px-3 py-2.5 text-xs font-medium cursor-pointer"
                        style={{ color: 'var(--text-secondary)', borderBottom: '1px solid var(--border-subtle)' }}
                      >
                        Sign out
                      </button>
                      <button
                        role="menuitem"
                        onClick={() => {
                          setMenuOpen(false)
                          setDeleteDialogOpen(true)
                        }}
                        className="w-full text-left px-3 py-2.5 text-xs font-medium cursor-pointer"
                        style={{ color: 'var(--accent-red)' }}
                      >
                        Delete account
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>
      </motion.header>

      <DeleteAccountDialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        isGoogleAccount={(user?.providerData ?? []).some((p) => p.providerId === 'google.com')}
        accountEmail={user?.email ?? ''}
      />

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
