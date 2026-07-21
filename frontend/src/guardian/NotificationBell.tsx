import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { useAuth } from '../auth/useAuth'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { useToast } from '../notifications/useToast'
import { formatRelativeTime } from './intakeApi'
import { makeNotificationsApi, type NotificationView } from './notificationsApi'
import { hasToasted, markSeen, readSeenRecord, recordToasted } from './notificationSeenStore'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'
import './guardian.css'

// Politely spaced, not urgent: this poll only refreshes the unread badge
// (and dedupes any newly-arrived alert into a toast); it is not the primary
// way a guardian discovers a safety-relevant notification, the toast is.
// 30s is well below IntakePage's 8s active-generation poll, which tracks a
// process the guardian is actively watching finish.
const POLL_MS = 30000

const PANEL_LIMIT = 30

const PANEL_LOAD_ERROR = 'We could not load your notifications. Please try again.'

type PanelState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: NotificationView[]; syncedAt: number }

function BellIcon() {
  return (
    <svg
      className="notification-bell__icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2Zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2Z"
      />
    </svg>
  )
}

/**
 * Guardian notification bell (register G10). A read-only projection of
 * pipeline_event surfaced via GET /v1/notifications; the backend keeps no
 * read/unread state for this first slice (notifications/api.py's docstring),
 * so this component owns the whole client-side model via
 * notificationSeenStore.ts:
 *
 * - The badge count comes from a `since`-filtered poll (lastSeenAt), which
 *   doubles as "what's new since the guardian last opened the panel"; any
 *   alert-severity item among those results fires the toast channel once
 *   (deduped by event id, so a poll tick never re-toasts the same event).
 * - The panel itself always shows the last 30 notifications regardless of
 *   read state (a guardian should be able to scroll back through recent
 *   activity, not just "what's new"), and opening it marks everything up to
 *   the newest item as seen.
 */
export function NotificationBell() {
  const { principal } = useAuth()
  const api = useApi()
  const notificationsApi = useMemo(() => makeNotificationsApi(api), [api])
  const { showToast } = useToast()

  const [unreadCount, setUnreadCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [panel, setPanel] = useState<PanelState>({ kind: 'idle' })

  const containerRef = useRef<HTMLDivElement>(null)
  const toggleRef = useRef<HTMLButtonElement>(null)

  const subject = principal?.subject ?? null

  // #CRITICAL: security: kid flags, blocked requests, and failed generations
  // are safety-relevant and must reach the guardian even if they never open
  // the panel; this is the sole trigger for that toast. It runs on every
  // poll tick (and the story-requests-changed event) regardless of whether
  // the panel is open.
  // #VERIFY: NotificationBell.test.tsx "toasts a new alert exactly once"
  // and "does not re-toast an alert already recorded".
  const refreshUnread = useCallback(async () => {
    if (subject === null) return
    try {
      const since = readSeenRecord(subject).lastSeenAt ?? undefined
      const items = await notificationsApi.list({ since })
      setUnreadCount(items.length)
      for (const item of items) {
        if (item.severity === 'alert' && !hasToasted(subject, item.id)) {
          showToast(`${item.title}. ${item.body}`, { tone: 'info' })
          recordToasted(subject, item.id)
        }
      }
    } catch (err) {
      // Progressive enhancement, same tolerance as GuardianShell's
      // pending-count badge: a failed unread check must never surface as a
      // page-level error, it just leaves the badge stale until the next tick.
      console.error(
        'notification unread check failed:',
        err instanceof Error ? err.message : err
      )
    }
  }, [subject, notificationsApi, showToast])

  // #ASSUME: timing dependencies: the immediate check is deferred through
  // setTimeout(fn, 0) rather than called directly in the effect body; a
  // direct `void refreshUnread()` here would call an outside (useCallback)
  // setState-calling function synchronously from the effect body, which
  // react-hooks/set-state-in-effect flags as a cascading-render risk (the
  // established fix elsewhere in this codebase, e.g.
  // ModerationThresholdsPage.tsx and LibraryPage.tsx, inlines a fresh local
  // function instead; here the deferral keeps refreshUnread as the single
  // shared implementation for the interval tick, the story-requests-changed
  // listener below, and this initial check).
  useEffect(() => {
    if (subject === null) return undefined
    const initial = setTimeout(() => void refreshUnread(), 0)
    const id = setInterval(() => void refreshUnread(), POLL_MS)
    return () => {
      clearTimeout(initial)
      clearInterval(id)
    }
  }, [subject, refreshUnread])

  useEffect(() => {
    if (subject === null) return undefined
    const bump = () => void refreshUnread()
    window.addEventListener(STORY_REQUESTS_CHANGED_EVENT, bump)
    return () => window.removeEventListener(STORY_REQUESTS_CHANGED_EVENT, bump)
  }, [subject, refreshUnread])

  const loadPanel = useCallback(async () => {
    if (subject === null) return
    setPanel({ kind: 'loading' })
    try {
      const items = await notificationsApi.list({ limit: PANEL_LIMIT })
      setPanel({ kind: 'ready', items, syncedAt: Date.now() })
      // Newest first (the backend's contract): items[0] is the newest, or
      // undefined for an empty panel, in which case markSeen leaves the
      // stored lastSeenAt untouched.
      markSeen(subject, items[0]?.occurred_at ?? null)
      setUnreadCount(0)
    } catch (err) {
      console.error('notification panel load failed:', err instanceof Error ? err.message : err)
      setPanel({
        kind: 'error',
        message: classifyApiError(err, {
          transient: PANEL_LOAD_ERROR,
          server: PANEL_LOAD_ERROR,
        }).message,
      })
    }
  }, [subject, notificationsApi])

  function togglePanel() {
    setOpen((wasOpen) => {
      const next = !wasOpen
      if (next) void loadPanel()
      return next
    })
  }

  // #ASSUME: UI state: an open panel closes on Escape (focus returns to the
  // toggle) or a click outside the bell/panel, matching the dismissal
  // conventions of the rest of the app's overlays (Dialog.tsx's Escape
  // handling).
  // #VERIFY: NotificationBell.test.tsx "closes on Escape" and "closes on an
  // outside click".
  useEffect(() => {
    if (!open) return undefined
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false)
        toggleRef.current?.focus()
      }
    }
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('mousedown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('mousedown', onPointerDown)
    }
  }, [open])

  if (subject === null) return null

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        ref={toggleRef}
        type="button"
        className="notification-bell__toggle"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        onClick={togglePanel}
      >
        <BellIcon />
        {unreadCount > 0 ? (
          <span className="notification-bell__badge" aria-hidden="true">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="notification-bell__panel" role="dialog" aria-label="Notifications">
          <h2 className="notification-bell__panel-title">Notifications</h2>
          {panel.kind === 'idle' || panel.kind === 'loading' ? (
            <p role="status" aria-live="polite" className="notification-bell__status">
              Loading…
            </p>
          ) : panel.kind === 'error' ? (
            <ErrorBanner className="notification-bell__error" onRetry={() => void loadPanel()}>
              {panel.message}
            </ErrorBanner>
          ) : panel.items.length === 0 ? (
            <p className="notification-bell__empty cyo-text-muted">Nothing here yet.</p>
          ) : (
            <ul className="notification-bell__list">
              {panel.items.map((item) => {
                const ago = formatRelativeTime(item.occurred_at, panel.syncedAt)
                return (
                  <li
                    key={item.id}
                    className={`notification-bell__item notification-bell__item--${item.severity}`}
                  >
                    {item.severity === 'alert' ? (
                      <span className="notification-bell__item-tag">Alert</span>
                    ) : null}
                    <span className="notification-bell__item-title">{item.title}</span>
                    <span className="notification-bell__item-body">{item.body}</span>
                    {ago !== null ? (
                      <span
                        className="notification-bell__item-age cyo-text-muted"
                        title={new Date(item.occurred_at).toLocaleString()}
                      >
                        {ago}
                      </span>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  )
}
