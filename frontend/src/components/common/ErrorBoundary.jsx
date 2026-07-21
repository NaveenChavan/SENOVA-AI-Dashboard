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
      return (
        <div className="card-gradient rounded-xl p-6 text-center">
          <svg className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--accent-amber)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>Chart rendering error</p>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>A temporary issue occurred. The rest of the dashboard is unaffected.</p>
        </div>
      )
    }

    return this.props.children
  }
}
