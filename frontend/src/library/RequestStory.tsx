import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isAxiosError } from 'axios'

import { Button } from '@ds/components/Button'
import { useApi } from '../hooks/useApi'
import {
  makeKidStoryRequestApi,
  type KidStoryRequest,
  type StoryRequestStatus,
} from './storyRequestApi'

// 'approved' is handled separately below (K12): it splits into a
// "being written" / "it's on your shelf" pair instead of one static line.
const STATUS_COPY: Record<Exclude<StoryRequestStatus, 'approved'>, string> = {
  pending: 'Waiting for a grown-up to say yes',
  declined: 'Not this time. Try another idea!',
  blocked: "Let's try a different idea!",
}

type SendError = 'busy' | 'generic' | 'anchor'

export interface ContinueAnchor {
  id: string
  title: string
}

// W0.4: an approved request's card flips from "being written" to "it's on
// your shelf" only once BOTH backend facts hold: the request carries a
// resulting_storybook_id (stamped by publishing/service.py::approve() at
// publish time, so it always names a fully moderated, human-approved book;
// see that field's #ASSUME on api/story_requests.py::_to_view) AND that id
// is present in this profile's own library list (a published book is not
// necessarily assigned to this child yet). Replaces the retired
// isLikelyPublished substring-match guess against shelf titles, which had
// no real backend link to work from.
function isPublishedToShelf(resultingStorybookId: string | null, libraryIds: string[]): boolean {
  return resultingStorybookId !== null && libraryIds.includes(resultingStorybookId)
}

/**
 * Kid "Request a story" affordance for the library page (Task 3.0). Age-
 * appropriate: a single button opens a short idea box; the list below shows the
 * child their own request statuses in friendly language. No moderation detail is
 * ever shown to the child. Mounting this on the library page is a separate task
 * (K3); this component only needs a profileId.
 *
 * WS-B PR 3: an optional `anchor` (a series-tagged book the child tapped
 * "Ask for the next book" on) opens the form pre-set to request a continuation
 * of that book instead of a new series name.
 *
 * K12/W0.4: `libraryIds` (the profile's current shelf storybook ids, already
 * fetched by LibraryPage) lets an 'approved' request distinguish "being
 * written" from "it's on your shelf" without any new backend call; see
 * isPublishedToShelf for the real resulting_storybook_id/library-membership
 * check. Defaults to an empty list so every approved request reads as
 * "being written" when the caller has no shelf data to offer.
 */
export function RequestStory({
  profileId,
  anchor = null,
  onClearAnchor,
  libraryIds = [],
  openSignal = 0,
}: {
  profileId: string
  anchor?: ContinueAnchor | null
  onClearAnchor?: () => void
  libraryIds?: string[]
  /** Bumped by the parent (the shelf's "Ask for a new story" tile) to open
   * the idea form from afar, exactly like tapping the form's own button:
   * clears any stale error, preserves anything already typed. */
  openSignal?: number
}) {
  const api = useApi()
  const requestApi = useMemo(() => makeKidStoryRequestApi(api), [api])
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [seriesTitle, setSeriesTitle] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<SendError | null>(null)
  const [requests, setRequests] = useState<KidStoryRequest[]>([])

  // #ASSUME: UI state: the child can tap "Ask for the next book" on the
  // library page while this form is closed (or already open on a different
  // idea); the parent hands a fresh anchor object on every tap, including a
  // repeat tap on the same book. A title typed before the anchor was set (or
  // after it was cleared) must not silently survive the switch into
  // continuation mode and get submitted as an unintended
  // proposed_series_title; likewise an error from an earlier attempt must not
  // greet the child on this fresh open (debt U1).
  // #VERIFY: comparing against the previous anchor reference during render
  // (React's documented "adjusting state" escape hatch) opens the form and
  // clears any pending seriesTitle and stale error on every new non-null
  // anchor, without a setState-in-effect cascade; a fresh object reference
  // from the parent, not a fresh book id, is what drives this, so tapping the
  // same book twice in a row still reopens a closed form.
  const [lastAnchor, setLastAnchor] = useState<ContinueAnchor | null>(null)
  if (anchor !== lastAnchor) {
    setLastAnchor(anchor)
    if (anchor !== null) {
      setOpen(true)
      setSeriesTitle('')
      setError(null)
    }
  }

  // Same render-adjust pattern as the anchor above: a bumped openSignal
  // opens the form with a clean error slate, mirroring the form's own
  // "Request a story" button. Unlike the anchor path it clears neither the
  // idea text nor the series title: the child may have typed, wandered off
  // to browse, and come back via the shelf tile.
  const [lastOpenSignal, setLastOpenSignal] = useState(openSignal)
  if (openSignal !== lastOpenSignal) {
    setLastOpenSignal(openSignal)
    if (openSignal > 0) {
      setOpen(true)
      setError(null)
    }
  }

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
      const extras = anchor
        ? { anchorStorybookId: anchor.id }
        : seriesTitle.trim().length > 0
          ? { proposedSeriesTitle: seriesTitle.trim() }
          : {}
      await requestApi.create(profileId, idea, extras)
      setText('')
      setSeriesTitle('')
      setOpen(false)
      onClearAnchor?.()
      await refreshAfterSend()
    } catch (err) {
      console.error('story request failed', err instanceof Error ? err.message : err)
      const status = isAxiosError(err) ? err.response?.status : undefined
      const isCapReached = status === 409
      // #ASSUME: external resources: an anchored submit can fail because the
      // anchor storybook is gone or no longer eligible (404/422) by the time
      // the request lands, not just from a generic backend error.
      // #VERIFY: the anchor is cleared on that failure so a retry sends a
      // fresh (anchor-less) request instead of resending the same anchor and
      // guaranteeing another failure.
      const isStaleAnchor = anchor !== null && (status === 404 || status === 422)
      if (isMountedRef.current) {
        setError(isCapReached ? 'busy' : isStaleAnchor ? 'anchor' : 'generic')
      }
      if (isStaleAnchor) onClearAnchor?.()
    } finally {
      if (isMountedRef.current) setSaving(false)
    }
  }

  function cancel() {
    setOpen(false)
    setText('')
    setSeriesTitle('')
    setError(null)
    onClearAnchor?.()
  }

  return (
    <section className="request-story" aria-label="Request a story">
      {open ? (
        <div className="request-story__form">
          <label className="request-story__label">
            What should your story be about?
            {/* A playful example so a child who freezes at a blank box sees
                the kind of answer that works; it disappears the moment they
                type, and Send stays disabled until they write their own. */}
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={500}
              rows={3}
              placeholder="A dragon who loves pancakes…"
            />
          </label>
          {anchor ? (
            <p className="request-story__continuing">
              Continuing: {anchor.title}{' '}
              <Button variant="ghost" disabled={saving} onClick={() => onClearAnchor?.()}>
                Not this one
              </Button>
            </p>
          ) : (
            <label className="request-story__label">
              Part of a series? Give it a name! (optional)
              <input
                type="text"
                value={seriesTitle}
                onChange={(e) => setSeriesTitle(e.target.value)}
                maxLength={120}
              />
            </label>
          )}
          {error === 'busy' ? (
            <p role="alert" className="request-story__error">
              You have lots of ideas waiting already! Wait for a few to be looked at before sending
              more.
            </p>
          ) : error === 'anchor' ? (
            <p role="alert" className="request-story__error">
              That story can&apos;t be continued right now. Pick another one, or send a new idea!
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
            <Button variant="ghost" disabled={saving} onClick={cancel}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button
          size="lg"
          onClick={() => {
            // Debt U1: a rejection that lands after the form has closed can
            // re-arm `error`; opening always starts from a clean slate so a
            // stale message never greets the child (debt T3 pins this).
            setError(null)
            setOpen(true)
          }}
        >
          Request a story
        </Button>
      )}
      {requests.length > 0 ? (
        <div className="request-story__status">
          <h2 className="request-story__list-heading">My requests</h2>
          <ul className="request-story__list">
            {requests.map((req) => {
              // UX-K3: the child's own idea, quoted, so pending rows are
              // distinguishable regardless of the request's lifecycle state.
              const idea = req.request_text ?? ''
              const ideaSpan = idea ? (
                <span className="request-story__item-idea">
                  {'“'}
                  {idea.length > 80 ? `${idea.slice(0, 80)}…` : idea}
                  {'”'}
                </span>
              ) : null
              // W1.4 (K19 reflect-back, design review 4.1): a short "we heard
              // you" line under a pending or approved request only -- a
              // declined/blocked row already gets its own honest STATUS_COPY
              // line ("Not this time...", "Let's try a different idea!"),
              // and layering a generic "We could not build this wish yet"
              // reflection on top of that would read as confusing, not warm.
              // req.kidSummary is a single pre-rendered, echo-safe sentence
              // (see storyRequestApi.ts::KidStoryRequest.kidSummary's own doc
              // for why this field, not the per-element list, was chosen);
              // null for a request with no stored interpretation (pre-WS-7),
              // so the line is simply omitted rather than showing "We heard:"
              // with nothing after it.
              const heard =
                (req.status === 'pending' || req.status === 'approved') && req.kidSummary ? (
                  <span className="request-story__item-status">We heard you: {req.kidSummary}</span>
                ) : null
              if (req.status !== 'approved') {
                return (
                  <li key={req.id} data-status={req.status} className="request-story__item">
                    {ideaSpan}
                    <span className="request-story__item-status">{STATUS_COPY[req.status]}</span>
                    {heard}
                  </li>
                )
              }
              const published = isPublishedToShelf(req.resultingStorybookId, libraryIds)
              return (
                <li
                  key={req.id}
                  data-status={published ? 'published' : 'generating'}
                  className="request-story__item"
                >
                  {ideaSpan}
                  {published ? (
                    "It's on your shelf!"
                  ) : (
                    <span className="request-story__generating">
                      {/* Decorative only; the text alone carries the meaning
                          (stilled entirely under prefers-reduced-motion, see
                          library.css). */}
                      <span className="request-story__generating-dots" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </span>
                      Your story is being written…
                    </span>
                  )}
                  {heard}
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </section>
  )
}
