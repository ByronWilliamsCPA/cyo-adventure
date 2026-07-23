---
title: "Offline and Conflict UX (Phase 1 Reader)"
schema_type: common
status: draft
owner: core-maintainer
purpose: >-
  Define the copy and wireframes for the multi-device 409 conflict dialog and the
  iOS post-eviction download-needed state, so the Playwright reconciliation test
  asserts the real UX.
tags:
  - architecture
  - specifications
  - development
---

This document specifies the reader's offline and sync UX for Phase 1. It is
written before the Playwright reconciliation test so the test asserts the real
copy and behaviour, not a placeholder. It covers two states: the multi-device
save conflict (HTTP 409) and the iOS post-eviction "download needed" state.

See [roadmap Phase 1](../planning/roadmap.md) and the multi-device sync rules in
the [tech spec](../planning/tech-spec.md).

## Principles

- The server is canonical; IndexedDB is a cache. On adult surfaces, progress is
  never silently lost. On the child reader path this principle was deliberately
  relaxed: see the Section 1 supersession note below.
- Children see plain, reassuring language. No technical terms (no "revision",
  "409", "sync token").
- Every choice the reader makes is saved immediately when online, and queued when
  offline and replayed on reconnect.

## 1. Multi-device save conflict (HTTP 409)

> **Superseded for the child reader (2026-07-22).** The conflict dialog, wireframe,
> and "modal, blocks play, no silent default" behaviour specified in this section
> were the original Phase 1 design. They have been replaced on the child reading
> path by silent newest-write-wins: a 409 adopts the server's current row without
> ever showing a dialog, because a 5-10 year old cannot reason about a "which place
> do you want to keep?" prompt and reading must never block on a conflict. This can
> discard the local position (deliberate, bounded data loss). The decision is
> recorded in
> [handoff-e2e-workflow-logic-review-2026-07-22.md](../planning/handoff-e2e-workflow-logic-review-2026-07-22.md)
> and implemented in `frontend/src/offline/sync.ts` (`resolveConflict`,
> `use_newer_progress` branch) and the 409 handler in
> `frontend/src/reader/ReaderPage.tsx`. The `continue_from_this_device` /
> `use_newer_progress` server contract below is unchanged; only the client no
> longer prompts. The copy and wireframe here are retained for historical context
> and would apply only if an adult-facing conflict surface is ever built.

Triggered when a `PUT /reading-state/{profile}/{story}` returns 409 because
another device advanced the same story since this device last synced. The server
returns the current row; the client must let the reader choose how to reconcile.

### Copy (conflict)

- Title: "You were reading on another device"
- Body: "Your place in this story is different here than on your other device.
  Which one do you want to keep?"
- Primary button: "Keep this device" (continue from the local position; the
  client re-saves at the server's current revision, overwriting the server copy)
- Secondary button: "Use the newest place" (adopt the server's position; the
  local position is discarded)

These two actions map to the server-contract options `continue_from_this_device`
and `use_newer_progress`.

### Wireframe (conflict)

```text
+--------------------------------------------------+
|              You were reading on                 |
|                another device                    |
|                                                  |
|  Your place in this story is different here than  |
|  on your other device. Which one do you want to   |
|  keep?                                            |
|                                                  |
|   [ Keep this device ]   [ Use the newest place ]|
+--------------------------------------------------+
```

### Behaviour (conflict)

- "Keep this device": resend the local save with `state_revision` set to the
  server's current revision (from the 409 body), so it applies cleanly and wins.
- "Use the newest place": replace the local reading state with the 409 body's
  `current_row` and resume the reader there.
- The dialog is modal and blocks play until the reader chooses; there is no
  silent default, so no progress is lost without a decision.

## 2. iOS post-eviction "download needed" state

iOS may evict a PWA's cached data under storage pressure. When the reader opens a
story whose blob is no longer in the IndexedDB/Cache Storage, the app cannot play
it offline and must re-download it.

### Copy (download)

- Title: "This story needs to download again"
- Body: "Your device cleared this story to save space. Connect to the internet to
  download it again."
- Primary button: "Try again" (re-fetch the story; on success, cache and open it)
- Secondary link: "Back to library"

### Wireframe (download)

```text
+--------------------------------------------------+
|         This story needs to download again       |
|                                                  |
|  Your device cleared this story to save space.   |
|  Connect to the internet to download it again.   |
|                                                  |
|        [ Try again ]      Back to library        |
+--------------------------------------------------+
```

### Behaviour (download)

- On reader open, look up the story blob in the cache. If absent and the network
  is unavailable, show this state instead of a broken passage.
- The app calls `navigator.storage.persist()` to request durable storage, but
  does not trust it on iOS (it is best-effort); IndexedDB remains a cache only.
- "Try again" re-fetches `GET /storybooks/{id}/versions/{v}`, re-caches the blob,
  and opens the reader at the last known reading state.

## Acceptance (asserted by the Playwright E2E)

- US-101 offline play: a downloaded story plays to an ending with the network
  disabled; the completion syncs on reconnect.
- Save/resume: progress survives a reload.
- Conflict: a two-device save race surfaces the dialog above; choosing "Keep this
  device" or "Use the newest place" resolves it without silent loss.
