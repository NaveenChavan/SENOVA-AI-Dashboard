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
      <header className="bg-slate-950/80 backdrop-blur-md border-b border-slate-800/60 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/upload" className="text-xl font-bold tracking-tight text-emerald-400 glow-emerald-text">
            SENOVA
            <span className="text-slate-100 font-light"> AI</span>
          </Link>
          <nav className="flex gap-1">
            {navLinks.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  pathname.startsWith(to)
                    ? 'bg-emerald-500/10 text-emerald-400'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`}
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-8">
        <AppRoutes />
      </main>

      <footer className="text-center text-xs text-slate-600 py-4 border-t border-slate-800/60">
        SENOVA AI Dashboard &mdash; Enterprise Preview
      </footer>
    </div>
  )
}
