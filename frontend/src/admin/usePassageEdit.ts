/**
 * G6 passage-edit dialog state for ReviewDetailPage: opens/closes the dialog
 * from the current surface's blob, tracks the editable fields, and saves via
 * the passage-edit API. Owns only its own dialog/form state; the review
 * surface itself stays owned by ReviewDetailPage's `[state, setState]`. On a
 * successful save this hook does NOT keep its own copy of the refreshed
 * surface: it calls `onSurfaceRefreshed`, which ReviewDetailPage wires to
 * `setState({ kind: 'ready', surface: refreshed })`.
 */
import { useState } from 'react'

import { classifyApiError } from '../hooks/classifyApiError'
import type { ReviewSurface } from '../guardian/reviewApi'
import { asGateFailure, type GateFindingView, type PassageEditApi } from './passageEditApi'
import { findEditableNode, type EditableChoice } from './reviewDiff'

export interface UsePassageEditParams {
  storybookId: string
  /** The current ready surface, or null while the surface has not loaded yet. */
  surface: ReviewSurface | null
  passageEditApi: PassageEditApi
  /** Pushes a successful edit's refreshed surface back up to the parent's single state slot. */
  onSurfaceRefreshed: (refreshed: ReviewSurface) => void
}

export interface UsePassageEditResult {
  editNodeId: string | null
  editBody: string
  editChoices: EditableChoice[]
  editSubmitting: boolean
  editError: string | null
  editGateFindings: GateFindingView[] | null
  editBodyValid: boolean
  /** G6: an edit is offered only while the backend would accept one (in_review or needs_revision). */
  editingDisabled: boolean
  openEditDialog: (nodeId: string) => void
  closeEditDialog: () => void
  setEditBody: (body: string) => void
  setEditChoiceLabel: (choiceId: string, label: string) => void
  saveEdit: () => Promise<void>
}

export function usePassageEdit({
  storybookId,
  surface,
  passageEditApi,
  onSurfaceRefreshed,
}: UsePassageEditParams): UsePassageEditResult {
  const [editNodeId, setEditNodeId] = useState<string | null>(null)
  const [editBody, setEditBody] = useState('')
  const [editChoices, setEditChoices] = useState<EditableChoice[]>([])
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editGateFindings, setEditGateFindings] = useState<GateFindingView[] | null>(null)

  // G6: an edit is offered only while the backend would accept one (in_review
  // or needs_revision); mirrors the Approve/Send Back status guard that lives
  // in ReviewDetailPage's actionbar. `surface === null` (the page has not
  // finished loading) disables it the same as any other non-editable status.
  const editingDisabled =
    surface === null || (surface.status !== 'in_review' && surface.status !== 'needs_revision')
  const editBodyValid = editBody.trim().length >= 1

  function openEditDialog(nodeId: string) {
    if (!surface) return
    const found = findEditableNode(surface.blob, nodeId)
    if (!found) return
    setEditNodeId(nodeId)
    setEditBody(found.body)
    setEditChoices(found.choices)
    setEditError(null)
    setEditGateFindings(null)
  }

  function closeEditDialog() {
    setEditNodeId(null)
    setEditError(null)
    setEditGateFindings(null)
    setEditSubmitting(false)
  }

  function setEditChoiceLabel(choiceId: string, label: string) {
    setEditChoices((current) => current.map((c) => (c.id === choiceId ? { ...c, label } : c)))
  }

  async function saveEdit() {
    if (editNodeId === null || surface === null) return
    setEditSubmitting(true)
    setEditError(null)
    setEditGateFindings(null)
    try {
      const refreshed = await passageEditApi.editNode(storybookId, surface.version, editNodeId, {
        body: editBody,
        ...(editChoices.length > 0
          ? { choice_labels: Object.fromEntries(editChoices.map((c) => [c.id, c.label])) }
          : {}),
      })
      onSurfaceRefreshed(refreshed)
      closeEditDialog()
    } catch (err) {
      // Log the message, not the axios error object (its config.headers
      // carries the caller's Authorization bearer token).
      console.error('passage edit failed:', err instanceof Error ? err.message : err)
      const gateFailure = asGateFailure(err)
      if (gateFailure) {
        setEditGateFindings(gateFailure.findings)
      } else {
        setEditError(
          classifyApiError(err, {
            transient: 'We could not save this edit. Please try again.',
            server: 'We could not save this edit. Please try again.',
          }).message
        )
      }
      setEditSubmitting(false)
    }
  }

  return {
    editNodeId,
    editBody,
    editChoices,
    editSubmitting,
    editError,
    editGateFindings,
    editBodyValid,
    editingDisabled,
    openEditDialog,
    closeEditDialog,
    setEditBody,
    setEditChoiceLabel,
    saveEdit,
  }
}
