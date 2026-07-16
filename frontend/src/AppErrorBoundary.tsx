import { Component, type ErrorInfo, type ReactNode } from 'react'

import './routeElements.css'

export interface AppErrorBoundaryProps {
  children: ReactNode
}

interface AppErrorBoundaryState {
  hasError: boolean
}

/**
 * Last-resort render-time error boundary, wrapping the whole routed app.
 *
 * React error boundaries only catch errors thrown during rendering, in
 * lifecycle methods, and in constructors of the tree below them; they do
 * NOT catch errors thrown from event handlers (those need their own
 * try/catch at the call site, e.g. the reader's applyChoice action in
 * player/machine.ts) or from async code. This boundary is the net for
 * everything else: an unexpected render-time throw anywhere in the routed
 * tree, which would otherwise unmount React entirely and leave a blank
 * screen with no way back for whoever is using the app.
 *
 * Deliberately a class component: React has no hook-based equivalent to
 * getDerivedStateFromError/componentDidCatch.
 */
export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // #EDGE: browser-compat: the underlying error may carry internal detail;
    // show a generic message to the user and log the specifics for diagnosis
    // (same stance as routeElements.tsx's RouteError).
    console.error('App crashed:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="route-not-found">
          <h1 className="route-not-found__title">Something went wrong.</h1>
          <p className="route-not-found__hint">
            Please reload the page. If the problem keeps happening, try again later.
          </p>
          <nav className="route-not-found__links" aria-label="Ways back in">
            <a className="route-not-found__link" href="/">
              Go to the start
            </a>
          </nav>
        </main>
      )
    }
    return this.props.children
  }
}
