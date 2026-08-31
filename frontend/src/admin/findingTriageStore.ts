import type { FindingView } from '../guardian/reviewApi'

/**
 * `RS-A5`: client-local per-finding triage for the admin review surface.
 *
 * A reviewer 60 findings into a book has no way to see where they are. This
 * stores a "reviewed" marker per finding, per book version, in the reviewer's
 * own browser.
 *
 * #CRITICAL: security: this state MUST NOT gate approval, and nothing here may
 * ever be read by the approve path. It is per-browser and lost on a cleared
 * cache or a device change (ruling 4, 2026-08-31: unresolved findings do not
 * gate a book; the reviewer does). A progress marker that silently became a
 * safety decision would let a cleared cache reset that decision, and the
 * backend would never know it had happened.
 * #VERIFY: ReviewDetailPage.test.tsx "marking every finding reviewed changes
 * nothing about approval" marks the whole list and asserts the override
 * requirement and the approve control are unchanged.
 *
 * Server-side triage is `RS-D1`, deliberately out of scope here rather than
 * deferred by accident: there is no stable finding id in the report schema,
 * and `api/remoderate.py` overwrites `version_row.moderation_report`
 * wholesale, so a server-side disposition would be silently orphaned by the
 * next re-moderation with no rule for what should happen to it.
 */

/**
 * Cap on stored markers per version, so a long session cannot grow the record
 * without bound. A book's whole report is far smaller than this; the cap is a
 * backstop against a pathological report, not a working limit.
 */
const MAX_MARKERS = 500

function storageKey(storybookId: string, version: number): string {
  return `cyo:review:triage:${storybookId}:${version}`
}

/**
 * A content-derived key for one finding.
 *
 * There is no stable finding id in the persisted report (design doc 2.1
 * persists findings as rows with no identifier), so the key is derived from
 * the fields that identify a finding within one report. Two consequences,
 * both intended:
 *
 * - A refetch of the same report reproduces the same keys, so markers survive
 *   a page reload and the surface refresh after a passage edit.
 * - A re-moderation that rewrites the report produces different keys for
 *   changed findings, so their markers simply stop matching. Orphaned markers
 *   are inert here precisely because this state gates nothing.
 *
 * #ASSUME: data integrity: two findings within one report that agree on every
 * field in this key are indistinguishable to a reviewer as well, so sharing a
 * marker is correct rather than lossy.
 * #VERIFY: findingTriageStore.test.ts "keys two identical findings the same
 * and any differing field apart".
 */
export function findingKey(finding: FindingView): string {
  return [
    finding.stage,
    finding.source,
    finding.category,
    finding.verdict,
    finding.severity ?? '',
    finding.node_id ?? '',
    finding.message,
  ].join('|')
}

/**
 * Read the reviewed-marker set for one book version.
 *
 * Degrades to an empty set when nothing is stored, storage is unavailable
 * (private browsing, a locked-down profile), or the stored value is not the
 * expected shape, the same tolerance `guardian/notificationSeenStore.ts`
 * applies. A reviewer whose browser refuses storage sees an untriaged list,
 * never a crashed review page.
 */
export function readReviewedKeys(storybookId: string, version: number): Set<string> {
  try {
    const raw = localStorage.getItem(storageKey(storybookId, version))
    if (raw === null) return new Set()
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((key): key is string => typeof key === 'string'))
  } catch {
    return new Set()
  }
}

function writeReviewedKeys(storybookId: string, version: number, keys: Set<string>): void {
  try {
    localStorage.setItem(
      storageKey(storybookId, version),
      JSON.stringify([...keys].slice(-MAX_MARKERS))
    )
  } catch {
    // #EDGE: browser-compat: storage unavailable or over quota. The caller's
    // in-memory set still drives this render, so the reviewer's session is
    // unaffected; only a reload loses the markers. Failing loudly here would
    // interrupt a review over a progress marker, which is the wrong trade.
  }
}

/**
 * Toggle one finding's reviewed marker, returning the new set.
 *
 * Returns a new Set rather than mutating, so a React caller can hold it in
 * state and get a re-render.
 */
export function toggleReviewed(
  storybookId: string,
  version: number,
  key: string,
  current: Set<string>
): Set<string> {
  const next = new Set(current)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  writeReviewedKeys(storybookId, version, next)
  return next
}
