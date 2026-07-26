import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary] Caught:', error, info)
  }

  render() {
    if (this.state.hasError) {
      // Compact, in-place fallback: one panel fails, the rest of the dashboard
      // keeps working, and the layout height barely changes.
      return (
        <div className="card card-pad text-center">
          <svg
            className="w-6 h-6 mx-auto mb-2"
            style={{ color: 'var(--accent-amber)' }}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-[13px] font-semibold mb-0.5" style={{ color: 'var(--text-primary)' }}>
            This panel failed to render
          </p>
          <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>
            The rest of the dashboard is unaffected.
          </p>
        </div>
      )
    }

    return this.props.children
  }
}
