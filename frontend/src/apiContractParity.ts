/**
 * Compile-time contract-parity guard for the hand-typed API adapters.
 *
 * Several adapters mirror the backend Pydantic response models by hand
 * (libraryApi.ts, recommendationsApi.ts, budgetApi.ts, ...) rather than calling
 * the generated client's request functions, because useApi()'s axios instance
 * carries the auth/refresh/correlation behavior those calls need. The generated
 * TYPES (src/client/types.gen.ts), however, are regenerated from the backend
 * OpenAPI schema and drift-checked in CI, so they are the source of truth for
 * wire shapes.
 *
 * This module asserts, at compile time, that each hand-typed view still matches
 * its generated counterpart. When a backend model changes and the client is
 * regenerated, `npm run typecheck` fails HERE until the hand-typed mirror is
 * updated. That closes the drift gap the CI client-drift job cannot see: those
 * adapters import nothing from the generated client at runtime, so a renamed or
 * retyped field would otherwise compile cleanly against a stale hand-typed view
 * and only surface in an e2e run or in production.
 *
 * There is no runtime output; these are type-level assertions only.
 */

import type { ChildEnvelopeUsage, FamilyBudgetView } from './guardian/budgetApi'
import type { LibraryItemView, LibraryProgressView, RatingView } from './library/libraryApi'
import type { RecommendationItem } from './library/recommendationsApi'
import type {
  ChildEnvelopeUsageView as GenChildEnvelopeUsage,
  FamilyBudgetView as GenFamilyBudgetView,
  LibraryItem as GenLibraryItem,
  LibraryProgress as GenLibraryProgress,
  RatingView as GenRatingView,
  RecommendationItem as GenRecommendationItem,
} from './client/types.gen'

/** Resolves to `true` only when X and Y are structurally identical, including
 * property optionality (the standard invariant type-equality idiom). */
type Equal<X, Y> =
  (<T>() => T extends X ? 1 : 2) extends <T>() => T extends Y ? 1 : 2 ? true : false

/** Compile error unless its argument resolves to `true`. */
type Expect<T extends true> = T

/**
 * One entry per hand-typed view. A failing entry means the backend model and
 * its hand-typed mirror have drifted: regenerate the client
 * (`npm run generate-client`) and update the adapter's interface to match.
 *
 * `LibraryItem` is compared with optionality normalized (`Required<>`): hey-api
 * marks Pydantic fields-with-defaults optional, but the backend always
 * serializes them, so the hand-typed view requires them. That artifact is not
 * drift; a renamed, removed, or retyped field still fails the check.
 */
export type ContractParityAssertions = [
  Expect<Equal<RatingView, GenRatingView>>,
  Expect<Equal<LibraryProgressView, GenLibraryProgress>>,
  Expect<Equal<Required<LibraryItemView>, Required<GenLibraryItem>>>,
  Expect<Equal<RecommendationItem, GenRecommendationItem>>,
  Expect<Equal<ChildEnvelopeUsage, GenChildEnvelopeUsage>>,
  Expect<Equal<FamilyBudgetView, GenFamilyBudgetView>>,
]
