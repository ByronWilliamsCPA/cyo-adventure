import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeProviderAllowlistApi } from './providerAllowlistApi'
import type { AllowlistListView } from '../client/types.gen'

// Mirrors generation.allowlist.ALLOWLIST_PROVIDERS / ProviderName in
// api/schemas.py ('mock' is a CI-only double, never allowlistable).
export const PROVIDERS = ['anthropic', 'openrouter', 'modal', 'ollama'] as const
export type ProviderValue = (typeof PROVIDERS)[number]

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
    return (
      <LoadingStatus />
    )
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
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function toggleEnabled(id: string, currentlyEnabled: boolean, currentDisplayName: string | null) {
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
    <main>
      <h1>Provider allowlist</h1>
      <p>
        Controls which (provider, model) pairs the generation pipeline is permitted to call.
        This is a global, cost-control setting, not tied to any one story; an admin picks the
        specific model for a story on the{' '}
        <Link to="/admin/authoring-queue">authoring queue</Link>, constrained to whatever is
        enabled here.
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
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={() => void toggleEnabled(row.id, row.enabled, row.display_name)}
                  >
                    {row.enabled ? `Disable ${row.model_id}` : `Enable ${row.model_id}`}
                  </button>
                  <button type="button" disabled={submitting} onClick={() => void remove(row.id)}>
                    Remove {row.model_id}
                  </button>
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
        <button type="submit" disabled={!canAdd}>
          Add to allowlist
        </button>
      </form>
    </main>
  )
}
