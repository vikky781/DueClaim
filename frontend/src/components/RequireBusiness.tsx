import { useCallback, useEffect, useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router'

import { api } from '../api/client'
import type { Business } from '../api/types'
import { BusinessContext, useBusiness } from '../lib/businessContext'
import { ErrorNote, Loading } from './ui'

type State = { status: 'loading' } | { status: 'ready'; business: Business | null } | { status: 'error'; error: unknown }

/**
 * Loads the business profile once per session and exposes it via context.
 * Routes nested under `gate` are redirected to /business until one exists.
 */
export function BusinessProvider() {
  const [state, setState] = useState<State>({ status: 'loading' })

  useEffect(() => {
    let alive = true
    api
      .getBusiness()
      .then((business) => alive && setState({ status: 'ready', business }))
      .catch((error: unknown) => alive && setState({ status: 'error', error }))
    return () => {
      alive = false
    }
  }, [])

  const setBusiness = useCallback((business: Business) => setState({ status: 'ready', business }), [])

  if (state.status === 'loading') return <Loading label="Loading your business profile" />
  if (state.status === 'error') return <ErrorNote error={state.error} onRetry={() => window.location.reload()} />

  return (
    <BusinessContext.Provider value={{ business: state.business, setBusiness }}>
      <Outlet />
    </BusinessContext.Provider>
  )
}

/** Wrap routes that need a business profile. */
export function RequireBusiness() {
  const { business } = useBusiness()
  const location = useLocation()
  if (!business) return <Navigate to="/business" replace state={{ from: location.pathname, reason: 'missing' }} />
  return <Outlet />
}
