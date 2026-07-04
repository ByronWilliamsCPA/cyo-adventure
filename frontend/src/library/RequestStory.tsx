import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { Button } from '@ds/components/Button'
import { useApi } from '../hooks/useApi'
import {
  makeKidStoryRequestApi,
  type KidStoryRequest,
  type StoryRequestStatus,
} from './storyRequestApi'

const STATUS_COPY: Record<StoryRequestStatus, string> = {
  pending: 'Waiting for a grown-up to say yes',
  approved: 'Yay! Your story is being made',
  declined: 'Not this time. Try another idea!',
  blocked: "Let's try a different idea!",
}

type SendError = 'busy' | 'generic'

/**
 * Kid "Request a story" affordance for the library page (Task 3.0). Age-
 * appropriate: a single button opens a short idea box; the list below shows the
 * child their own request statuses in friendly language. No moderation detail is
 * ever shown to the child. Mounting this on the library page is a separate task
 * (K3); this component only needs a profileId.
 */
export function RequestStory({ profileId }: { profileId: string }) {
  const api = useApi()
  const requestApi = useMemo(() => makeKidStoryRequestApi(api), [api])
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<SendError | null>(null)
  const [requests, setRequests] = useState<KidStoryRequest[]>([])

  // #ASSUME: timing dependencies: this component can unmount while a fetch or
  // submit is still in flight (profile switch, navigating away from the
  // library).
  // #VERIFY: every setState below checks isMountedRef first so a late
  // response never writes into an unmounted component.
  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const fetchRequests = useCallback(
    () => requestApi.listForProfile(profileId),
    [requestApi, profileId]
  )

  // #ASSUME: external resources: listForProfile can fail (network hiccup,
  // backend unavailable) or resolve after profileId has already changed
  // again (profile switch while this load is in flight).
  // #VERIFY: `cancelled` plus isMountedRef guard the setState so a late
  // response never clobbers a newer one; a failed background refresh
  // degrades silently (the status list just stays empty or stale) rather
  // than surfacing a scary error for a passive load, since the create path
  // already surfaces its own failure to the child.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const list = await fetchRequests()
        if (!cancelled && isMountedRef.current) setRequests(list)
      } catch (err) {
        console.error('load story requests failed', err instanceof Error ? err.message : err)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fetchRequests])

  const refreshAfterSend = useCallback(async () => {
    try {
      const list = await fetchRequests()
      if (isMountedRef.current) setRequests(list)
    } catch (err) {
      console.error('load story requests failed', err instanceof Error ? err.message : err)
    }
  }, [fetchRequests])

  // #CRITICAL: concurrency: the backend caps a profile at 5 pending requests
  // and returns 409 once it is hit; this button is the only writer for this
  // profile's requests, but a double-click before `saving` flips to true
  // would still fire two creates back to back.
  // #VERIFY: `saving` is set synchronously before the first await below, and
  // the Send button is disabled while `saving` is true.
  async function send() {
    if (saving) return
    const idea = text.trim()
    if (idea.length === 0) return
    setSaving(true)
    setError(null)
    try {
      await requestApi.create(profileId, idea)
      setText('')
      setOpen(false)
      await refreshAfterSend()
    } catch (err) {
      console.error('story request failed', err instanceof Error ? err.message : err)
      const isCapReached = isAxiosError(err) && err.response?.status === 409
      if (isMountedRef.current) setError(isCapReached ? 'busy' : 'generic')
    } finally {
      if (isMountedRef.current) setSaving(false)
    }
  }

  function cancel() {
    setOpen(false)
    setText('')
    setError(null)
  }

  return (
    <section className="request-story" aria-label="Request a story">
      {open ? (
        <div className="request-story__form">
          <label className="request-story__label">
            What should your story be about?
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={500}
              rows={3}
            />
          </label>
          {error === 'busy' ? (
            <p role="alert" className="request-story__error">
              You have lots of ideas waiting already! Wait for a few to be looked at before
              sending more.
            </p>
          ) : error === 'generic' ? (
            <p role="alert" className="request-story__error">
              Something went wrong. Try again!
            </p>
          ) : null}
          <div className="request-story__actions">
            <Button disabled={saving || text.trim().length === 0} onClick={() => void send()}>
              {saving ? 'Sending…' : 'Send'}
            </Button>
            <Button variant="ghost" onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button size="lg" onClick={() => setOpen(true)}>
          Request a story
        </Button>
      )}
      {requests.length > 0 ? (
        <div className="request-story__status">
          <h2 className="request-story__list-heading">My requests</h2>
          <ul className="request-story__list">
            {requests.map((req) => (
              <li key={req.id} data-status={req.status} className="request-story__item">
                {STATUS_COPY[req.status]}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
