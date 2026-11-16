import { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  handleReset = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="wrap min-h-[400px] py-16">
          <h2 className="h2 mb-2">
            Something went wrong
          </h2>
          <p className="text-body text-ink-2 mb-5">
            An unexpected error occurred. Please try again.
          </p>
          <button
            onClick={this.handleReset}
            className="btn"
          >
            Try Again
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
