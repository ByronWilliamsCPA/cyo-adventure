import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { Button } from '@ds/components/Button'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { makeProviderAllowlistApi } from './providerAllowlistApi'
import type { AllowlistCreateBody, AllowlistListView } from '../client/types.gen'

// Derived from the GENERATED contract rather than re-declared, so a backend
// change to ProviderName (api/schemas.py) that is regenerated into the client
// fails typecheck here instead of leaving this list silently stale.
// 'mock' is a CI-only double and is never allowlistable, so it is absent from
// the contract enum too.
export type ProviderValue = AllowlistCreateBody['provider']

// The derivation is exhaustive BY CONSTRUCTION, via a Record keyed by the
// union. A plain `readonly ProviderValue[]` annotation was not: an array type
// validates each element but accepts a SUBSET, so a provider ADDED to the
// contract would still have typechecked here while silently dropping out of
// the select -- which half-defeats deriving from the contract at all. A Record
// fails to compile on a missing key as well as on an unknown one, so the two
// cannot diverge in either direction. Key insertion order is the option order.
const PROVIDER_OPTIONS: Record<ProviderValue, true> = {
  anthropic: true,
  openrouter: true,
  modal: true,
}
const PROVIDERS = Object.keys(PROVIDER_OPTIONS) as ProviderValue[]

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: AllowlistListView }

/**
 * Admin-only settings page for the provider/model allowlist (billing/
 * cost-control gate on which (provider, model_id) pairs the generation
 * pipeline may call, WS-C PR #170). This is a global list, independent of
 * any single story; the per-request model choice happens on the authoring
 * queue (AuthoringQueuePage/AuthoringPlanDialog), which is validated
 * against these rows server-side. Registered admin-only in router.tsx,
 * mirroring ModerationThresholdsPage.
 */
export function ProviderAllowlistPage() {
  usePageTitle('Provider Allowlist')
  const api = useApi()
  const allowlistApi = useMemo(() => makeProviderAllowlistApi(api), [api])

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [provider, setProvider] = useState<ProviderValue>(PROVIDERS[0])
  const [modelId, setModelId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Mount-time load, matching ModerationThresholdsPage's cancelled-guard
  // idiom so an unmount before the request resolves never calls setState on
  // a gone component.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await allowlistApi.list()
        if (!cancelled) setState({ kind: 'ready', data })
      } catch (err) {
        console.error('allowlist list load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the provider allowlist. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [allowlistApi])

  async function refreshAfterMutation() {
    try {
      const data = await allowlistApi.list()
      setState({ kind: 'ready', data })
    } catch (err) {
      console.error('allowlist list refresh failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'That change saved, but the list could not refresh. Reload to see it.',
        }).message
      )
    }
  }

  if (state.kind === 'loading') {
    return <LoadingStatus />
  }
  if (state.kind === 'error') {
    return <ErrorBanner className="console__error">{state.message}</ErrorBanner>
  }

  const { data } = state
  const trimmedModelId = modelId.trim()
  const canAdd = trimmedModelId.length > 0 && !submitting

  async function add() {
    if (!canAdd) return
    setSubmitting(true)
    setActionError(null)
    try {
      await allowlistApi.create({
        provider,
        model_id: trimmedModelId,
        display_name: displayName.trim() || null,
      })
      setModelId('')
      setDisplayName('')
      await refreshAfterMutation()
    } catch (err) {
      console.error('allowlist create failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not add that entry. It may already be on the allowlist.',
          // Opts into classifyApiError's 422 handling (UW-C351): a 422 here is
          // the family-lane allowlist guard (commit d1fb0b7b), which returns a
          // specific, actionable reason in the response body. This string is
          // only the fallback for a 422 whose body can't be parsed.
          validation: 'We could not add that entry.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function toggleEnabled(
    id: string,
    currentlyEnabled: boolean,
    currentDisplayName: string | null
  ) {
    setSubmitting(true)
    setActionError(null)
    try {
      await allowlistApi.update(id, {
        enabled: !currentlyEnabled,
        display_name: currentDisplayName,
      })
      await refreshAfterMutation()
    } catch (err) {
      console.error('allowlist toggle failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not update that entry. Please try again.',
          // Opts into classifyApiError's 422 handling (UW-C351): re-enabling a
          // family-lane-forbidden row hits the same guard as create() above.
          validation: 'We could not update that entry.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function remove(id: string) {
    setSubmitting(true)
    setActionError(null)
    try {
      // The delete endpoint returns the full refreshed list view, so no
      // separate refreshAfterMutation() round-trip is needed.
      const refreshed = await allowlistApi.remove(id)
      setState({ kind: 'ready', data: refreshed })
    } catch (err) {
      console.error('allowlist delete failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not remove that entry. Please try again.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1>Provider allowlist</h1>
      <p>
        Controls which (provider, model) pairs the generation pipeline is permitted to call. This is
        a global, cost-control setting, not tied to any one story; an admin picks the specific model
        for a story on the <Link to="/admin/authoring-queue">authoring queue</Link>, constrained to
        whatever is enabled here.
      </p>
      {actionError ? <ErrorBanner className="console__error">{actionError}</ErrorBanner> : null}
      {data.rows.length === 0 ? (
        <p className="console__muted cyo-text-muted">No allowlist entries yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">Model id</th>
              <th scope="col">Display name</th>
              <th scope="col">Status</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.id}>
                <td>{row.provider}</td>
                <td>{row.model_id}</td>
                <td>{row.display_name ?? '-'}</td>
                <td>{row.enabled ? 'Enabled' : 'Disabled'}</td>
                <td>
                  <Button
                    variant={row.enabled ? 'danger' : 'ghost'}
                    disabled={submitting}
                    onClick={() => void toggleEnabled(row.id, row.enabled, row.display_name)}
                  >
                    {row.enabled ? `Disable ${row.model_id}` : `Enable ${row.model_id}`}
                  </Button>
                  <Button
                    variant="danger"
                    disabled={submitting}
                    onClick={() => void remove(row.id)}
                  >
                    Remove {row.model_id}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h2>Add an allowlist entry</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void add()
        }}
      >
        <label>
          Provider
          <select value={provider} onChange={(e) => setProvider(e.target.value as ProviderValue)}>
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model id
          <input
            type="text"
            value={modelId}
            maxLength={200}
            onChange={(e) => setModelId(e.target.value)}
            required
          />
        </label>
        <label>
          Display name (optional)
          <input
            type="text"
            value={displayName}
            maxLength={200}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>
        <Button type="submit" variant="primary" disabled={!canAdd}>
          Add to allowlist
        </Button>
      </form>
    </div>
  )
}
