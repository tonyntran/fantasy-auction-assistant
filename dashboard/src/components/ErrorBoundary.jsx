import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { hasError: false, error: null }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error(`[${this.props.name}] Error:`, error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card bg-base-200 shadow-md">
          <div className="card-body p-4">
            <p className="text-xs text-error">
              {this.props.name || 'Component'} failed to render
            </p>
            <button
              className="btn btn-xs btn-outline mt-1"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Retry
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
