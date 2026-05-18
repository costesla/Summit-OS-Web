/**
 * Global error boundary — catches unhandled React render errors.
 * Emits a structured telemetry event and renders a recovery UI
 * instead of a white screen.
 */
import React from 'react'
import telemetry, { EVENTS } from '../lib/telemetry'

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    telemetry.error(EVENTS.JS_ERROR, error.message, {
      stack: error.stack?.slice(0, 500),
      componentStack: info.componentStack?.slice(0, 500),
    })
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null })
    window.location.reload()
  }

  render() {
    if (!this.state.hasError) return this.props.children

    if (this.props.fallback) return this.props.fallback

    return (
      <div
        className="min-h-screen bg-[#111] flex items-center justify-center p-8"
        role="alert"
      >
        <div className="max-w-lg w-full rounded-2xl border border-rose-500/30 bg-rose-500/5 backdrop-blur p-8 text-center space-y-4">
          <div className="text-4xl">⚠️</div>
          <h1 className="text-xl font-black text-white">SummitOS encountered an error</h1>
          <p className="text-sm text-gray-400 font-mono">
            {this.state.error?.message ?? 'An unexpected error occurred.'}
          </p>
          <p className="text-xs text-gray-600 font-mono">
            This event has been logged to telemetry. Reload to recover.
          </p>
          <button
            onClick={this.handleReload}
            className="mt-4 px-6 py-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-bold text-sm hover:bg-cyan-500/20 transition-all"
          >
            Reload Dashboard
          </button>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
