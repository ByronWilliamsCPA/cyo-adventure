import { useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { classifyApiError } from '../hooks/classifyApiError'
import type { StoryRequestView } from '../guardian/storyRequestQueueApi'
import type { AllowlistView, AuthoringPlanRequest } from '../client/types.gen'

type Method = AuthoringPlanRequest['method']
type Mechanism = AuthoringPlanRequest['mechanism']

// Mirrors the backend's SKILL_MECHANISM_MODELS
// (story_requests/authoring_plan.py) exactly: the only Claude Code session
// models valid when mechanism='skill'. A free-text prep_model here would
// otherwise 422 with a confusing "not a recognized Claude Code session
// model" error (found live against a real backend, 2026-07-16) since this
// constraint doesn't apply to mechanism='automated_provider', where
// prep_model stays free text.
// #VERIFY: keep in sync by hand if authoring_plan.py's list changes; no
// automated check ties the two together (same caveat as the backend list).
const SKILL_MECHANISM_MODELS = [
  'sonnet',
  'opus',
  'fable',
  'haiku',
  'claude-sonnet-5',
  'claude-opus-4-8',
  'claude-fable-5',
  'claude-haiku-4-5-20251001',
] as const

interface AuthoringPlanDialogProps {
  request: StoryRequestView
  allowlistRows: AllowlistView[]
  onSubmit: (body: AuthoringPlanRequest) => Promise<void>
  onClose: () => void
}

/**
 * The admin's choice of authoring method/mechanism/model for one approved
 * story request (POST /story-requests/{id}/authoring-plan). Shows the
 * request's already-locked-in age_band/length/narrative_style (set earlier,
 * at request-approval time, by StoryRequestQueue) as read-only context; this
 * dialog only picks HOW the story gets written, not those fields.
 *
 * `review_stage1_model`/`review_stage2_model` (optional Stage 1/2 model
 * overrides, skeleton_fill only) are deliberately not exposed here: they're
 * optional fine-tuning knobs with sensible server-side defaults, and adding
 * every override would make this form unusable for its common case. An admin
 * who needs them can still call the API directly; this is a v1 admin UI, not
 * full API parity.
 */
export function AuthoringPlanDialog({
  request,
  allowlistRows,
  onSubmit,
  onClose,
}: AuthoringPlanDialogProps) {
  const [method, setMethod] = useState<Method>('skeleton_fill')
  const [mechanism, setMechanism] = useState<Mechanism>('skill')
  const [prepModel, setPrepModel] = useState<string>(SKILL_MECHANISM_MODELS[0])
  const [provider, setProvider] = useState('')
  const [modelId, setModelId] = useState('')
  const [skeletonSlug, setSkeletonSlug] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const enabledRows = useMemo(() => allowlistRows.filter((r) => r.enabled), [allowlistRows])
  const providers = useMemo(
    () => Array.from(new Set(enabledRows.map((r) => r.provider))),
    [enabledRows]
  )
  const modelsForProvider = useMemo(
    () => enabledRows.filter((r) => r.provider === provider),
    [enabledRows, provider]
  )

  // fresh_generation always pairs with automated_provider (the backend
  // rejects fresh_generation + skill at the schema boundary); switching to
  // fresh_generation while mechanism='skill' is selected must move the
  // mechanism forward too, or Save would submit an always-422 combination.
  function selectMethod(next: Method) {
    setMethod(next)
    if (next === 'fresh_generation' && mechanism === 'skill') {
      selectMechanism('automated_provider')
    }
  }

  // prep_model's valid values depend on which mechanism owns it (see the
  // SKILL_MECHANISM_MODELS comment above): reset to a value that's actually
  // valid for the new mechanism rather than carrying over one that would
  // 422 (a skill alias is meaningless as an automated_provider prep_model
  // sentinel, and an arbitrary free-text value is invalid for skill).
  function selectMechanism(next: Mechanism) {
    setMechanism(next)
    setPrepModel(next === 'skill' ? SKILL_MECHANISM_MODELS[0] : '')
  }

  async function save() {
    setSubmitting(true)
    setErrorMsg(null)
    try {
      const body: AuthoringPlanRequest = {
        method,
        mechanism,
        prep_model: prepModel.trim(),
        ...(mechanism === 'automated_provider'
          ? { provider: provider as AuthoringPlanRequest['provider'], model: modelId.trim() }
          : {}),
        ...(method === 'skeleton_fill' && skeletonSlug.trim().length > 0
          ? { skeleton_slug: skeletonSlug.trim() }
          : {}),
      }
      await onSubmit(body)
      onClose()
    } catch (err) {
      console.error('authoring plan create failed', err)
      setErrorMsg(
        classifyApiError(err, {
          transient:
            'We could not create the authoring plan. Check the model choice and try again.',
        }).message
      )
      setSubmitting(false)
    }
  }

  const prepModelValid = prepModel.trim().length > 0
  const automatedValid =
    mechanism !== 'automated_provider' || (provider.length > 0 && modelId.trim().length > 0)
  const valid = prepModelValid && automatedValid && !submitting

  return (
    <Dialog
      title={`Build authoring plan: ${request.request_text ?? 'this request'}`}
      onClose={onClose}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!valid}>
            Create plan
          </Button>
        </>
      }
    >
      <form
        className="authoring-plan-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (valid) void save()
        }}
      >
        {errorMsg ? (
          <p role="alert" className="authoring-plan-form__error cyo-text-error">
            {errorMsg}
          </p>
        ) : null}
        <dl className="authoring-plan-form__context">
          <dt>Age band</dt>
          <dd>{request.age_band}</dd>
          <dt>Length</dt>
          <dd>{request.length ?? 'not set'}</dd>
          <dt>Style</dt>
          <dd>{request.narrative_style}</dd>
        </dl>
        <fieldset>
          <legend>Method</legend>
          <label>
            <input
              type="radio"
              name="method"
              checked={method === 'skeleton_fill'}
              onChange={() => selectMethod('skeleton_fill')}
            />
            Fill an existing skeleton
          </label>
          <label>
            <input
              type="radio"
              name="method"
              checked={method === 'fresh_generation'}
              onChange={() => selectMethod('fresh_generation')}
            />
            Fresh generation
          </label>
        </fieldset>
        <fieldset>
          <legend>Mechanism</legend>
          <label>
            <input
              type="radio"
              name="mechanism"
              checked={mechanism === 'skill'}
              disabled={method === 'fresh_generation'}
              onChange={() => selectMechanism('skill')}
            />
            Human runs the cyo-author skill
          </label>
          <label>
            <input
              type="radio"
              name="mechanism"
              checked={mechanism === 'automated_provider'}
              onChange={() => selectMechanism('automated_provider')}
            />
            Automated provider
          </label>
        </fieldset>
        {mechanism === 'skill' ? (
          <label>
            Prep model
            <select value={prepModel} onChange={(e) => setPrepModel(e.target.value)}>
              {SKILL_MECHANISM_MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label>
            Prep model
            <input
              type="text"
              value={prepModel}
              onChange={(e) => setPrepModel(e.target.value)}
              required
            />
          </label>
        )}
        {mechanism === 'automated_provider' ? (
          <>
            <label>
              Provider
              <select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value)
                  setModelId('')
                }}
              >
                <option value="">Choose…</option>
                {providers.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Model
              <select
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                disabled={provider.length === 0}
              >
                <option value="">Choose…</option>
                {modelsForProvider.map((row) => (
                  <option key={row.id} value={row.model_id}>
                    {row.display_name ?? row.model_id}
                  </option>
                ))}
              </select>
            </label>
            {provider.length > 0 && modelsForProvider.length === 0 ? (
              <p className="authoring-plan-form__hint">
                No enabled allowlist entries for {provider}. Add one on the provider allowlist
                page first.
              </p>
            ) : null}
          </>
        ) : null}
        {method === 'skeleton_fill' ? (
          <label>
            Skeleton override (optional)
            <input
              type="text"
              value={skeletonSlug}
              onChange={(e) => setSkeletonSlug(e.target.value)}
              placeholder="Leave blank to auto-match"
            />
          </label>
        ) : null}
      </form>
    </Dialog>
  )
}
