/**
 * Compile-time contract-parity guard for the hand-typed API adapters.
 *
 * Several adapters mirror the backend Pydantic response models by hand
 * (libraryApi, recommendationsApi, budgetApi, intakeApi, reviewApi) rather than
 * calling the generated client's request functions, because useApi()'s axios
 * instance carries the auth/refresh/correlation behavior those calls need. The
 * generated TYPES (src/client/types.gen.ts), however, are regenerated from the
 * backend OpenAPI schema and drift-checked in CI, so they are the source of
 * truth for wire shapes.
 *
 * This module asserts, at compile time, that each hand-typed view still matches
 * its generated counterpart. When a backend model changes and the client is
 * regenerated, `npm run typecheck` fails HERE until the hand-typed mirror is
 * updated. That closes the drift gap the CI client-drift job cannot see: those
 * adapters import nothing from the generated client at runtime, so a renamed or
 * retyped field would otherwise compile cleanly against a stale hand-typed view
 * and only surface in an e2e run or in production.
 *
 * Two assertion strengths are used:
 * - `Equal` for views that are exact structural mirrors of the model.
 * - `BackendAcceptedBy` for views that intentionally widen a named union to
 *   `string` (e.g. a finding's `source`), asserting only that every value the
 *   backend can return is accepted by the view. That still catches a
 *   renamed/removed/retyped field the view reads, or a new enum member the view
 *   does not handle, while tolerating the deliberate looseness.
 *
 * There is no runtime output; these are type-level assertions only.
 */

import type { ChildEnvelopeUsage, FamilyBudgetView } from './guardian/budgetApi'
import type { ConceptCreated, GenerationEnqueued } from './guardian/intakeApi'
import type {
  ApprovedResult,
  FindingView,
  FlaggedPassage,
  ReviewQueueItem,
  ReviewSummary,
  ReviewSurface,
  SentBackResult,
} from './guardian/reviewApi'
import type { LibraryItemView, LibraryProgressView, RatingView } from './library/libraryApi'
import type { RecommendationItem } from './library/recommendationsApi'
import type {
  ApprovedView as GenApprovedView,
  ChildEnvelopeUsageView as GenChildEnvelopeUsage,
  ConceptCreatedResponse as GenConceptCreatedResponse,
  FamilyBudgetView as GenFamilyBudgetView,
  FindingView as GenFindingView,
  FlaggedPassage as GenFlaggedPassage,
  GenerationEnqueuedResponse as GenGenerationEnqueuedResponse,
  LibraryItem as GenLibraryItem,
  LibraryProgress as GenLibraryProgress,
  RatingView as GenRatingView,
  RecommendationItem as GenRecommendationItem,
  ReviewQueueItem as GenReviewQueueItem,
  ReviewSummary as GenReviewSummary,
  ReviewSurfaceView as GenReviewSurfaceView,
  SentBackView as GenSentBackView,
} from './client/types.gen'

/** Resolves to `true` only when X and Y are structurally identical, including
 * property optionality (the standard invariant type-equality idiom). */
type Equal<X, Y> =
  (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? true : false

/** Resolves to `true` when every value of `Backend` is accepted by `View`
 * (`Backend` is assignable to `View`). Catches a field the view reads being
 * renamed, removed, or retyped, and a union widened with a new member the view
 * does not handle, while tolerating a view that is intentionally looser than the
 * model (e.g. `string` where the model uses a named union). Tuple-wrapped to
 * suppress distribution over union members. */
type BackendAcceptedBy<View, Backend> = [Backend] extends [View] ? true : false

/** Compile error unless its argument resolves to `true`. */
type Expect<T extends true> = T

/**
 * One entry per guarded view. A failing entry means the backend model and its
 * hand-typed mirror have drifted: regenerate the client
 * (`npm run generate-client`) and update the adapter's interface to match.
 *
 * `LibraryItem` and `GenerationEnqueued` are compared with optionality
 * normalized (`Required<>`): hey-api marks Pydantic fields-with-defaults
 * optional, but the backend always serializes them, so the hand-typed view
 * requires them. That artifact is not drift; a renamed, removed, or retyped
 * field still fails the check.
 */
export type ContractParityAssertions = [
  // Exact mirrors.
  Expect<Equal<RatingView, GenRatingView>>,
  Expect<Equal<LibraryProgressView, GenLibraryProgress>>,
  Expect<Equal<Required<LibraryItemView>, Required<GenLibraryItem>>>,
  Expect<Equal<RecommendationItem, GenRecommendationItem>>,
  Expect<Equal<ChildEnvelopeUsage, GenChildEnvelopeUsage>>,
  Expect<Equal<FamilyBudgetView, GenFamilyBudgetView>>,
  Expect<Equal<ReviewSummary, GenReviewSummary>>,
  Expect<Equal<ReviewQueueItem, GenReviewQueueItem>>,
  Expect<Equal<ConceptCreated, GenConceptCreatedResponse>>,
  Expect<Equal<Required<GenerationEnqueued>, Required<GenGenerationEnqueuedResponse>>>,
  // Loose mirrors: the view widens a named union to `string` (finding source,
  // approve/send-back status literal), so assert only backend-accepted-by-view.
  Expect<BackendAcceptedBy<ApprovedResult, GenApprovedView>>,
  Expect<BackendAcceptedBy<SentBackResult, GenSentBackView>>,
  Expect<BackendAcceptedBy<FindingView, GenFindingView>>,
  Expect<BackendAcceptedBy<FlaggedPassage, GenFlaggedPassage>>,
  Expect<BackendAcceptedBy<ReviewSurface, GenReviewSurfaceView>>,
]

/*
 * Intentionally NOT compile-guarded here, and why:
 *
 * - ConceptBriefBody / Protagonist (intakeApi): request bodies. The frontend
 *   sends a deliberate SUBSET of the model ConceptBrief (it omits `length`,
 *   `narrative_style`, and `anchor_context`, relying on backend defaults) and
 *   types some fields more loosely (`structure_pattern: string` vs the model's
 *   `StructurePattern` union), so strict parity would fight the design. A wrong
 *   request body 422s loudly at runtime and is covered by the e2e-real tier,
 *   unlike a silent read-drift.
 *
 * - GenerationJobSummary (intakeApi) vs GenerationJobListItem: the view narrows
 *   `storybook_status` (backend `string`) to a union, so it cannot be
 *   backend-accepted-by-view without widening the view and losing that typing.
 *   This comparison also surfaced real drift: the backend `status` union gained
 *   `awaiting_manual_fill`, which the view's `JobStatus` does not list. Left for
 *   a maintainer decision (add the member and map it in `statusPill`), since the
 *   pill mapping is a UX choice, not a mechanical type fix.
 */
