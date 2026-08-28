/**
 * Seeded PRNG substrate for the usersim walk tier (mulberry32).
 *
 * Inlined deliberately, with no npm dependency: this tier's whole value
 * proposition is that a finding can be replayed exactly, which must not
 * depend on some dependency's own RNG changing under us across a version
 * bump. mulberry32 is a small, well-known 32-bit generator; the
 * implementation below is the standard one.
 *
 * Determinism is the design centre of this tier: a finding that cannot be
 * reproduced by re-running with the same USERSIM_SEED is not a bug report,
 * it is a rumour.
 */

/**
 * Fixed fallback seed, used whenever USERSIM_SEED is unset or does not
 * parse, so a CI run (which will not have USERSIM_SEED set) is still fully
 * deterministic without extra configuration.
 */
export const DEFAULT_SEED = 0x5eed_1234

function readSeedFromEnv(): number | undefined {
  // #ASSUME: external-resources: process.env may not exist at all in a
  // browser evaluation context. This module is imported only from
  // Playwright's Node-side test/support code (never injected into a page),
  // so process is expected to be defined wherever this actually runs; the
  // guard below is only so importing this file never throws in a context
  // where it happens not to be.
  // #VERIFY: personas.ts and the walk driver (task 2) import this only from
  // Playwright spec/support files, never via page.addInitScript or similar.
  const raw = typeof process !== 'undefined' && process.env ? process.env.USERSIM_SEED : undefined
  if (raw === undefined || raw === '') return undefined
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed >>> 0 : undefined
}

/**
 * The seed actually in effect for this process: USERSIM_SEED when it parses
 * to a finite number, DEFAULT_SEED otherwise. Exported so a later task can
 * print it on failure; a finding's replay instructions need the real seed
 * that was used, not the environment variable that may or may not have been
 * set.
 */
export const RESOLVED_SEED: number = readSeedFromEnv() ?? DEFAULT_SEED

export interface SeededRng {
  readonly seed: number
  /** Next pseudo-random float in [0, 1). */
  next(): number
  /** Next pseudo-random integer in [0, maxExclusive). */
  nextInt(maxExclusive: number): number
  /** Pick one element of a non-empty array. */
  pick<T>(items: readonly T[]): T
}

/**
 * mulberry32, a small, fast 32-bit PRNG (public-domain design by Tommy
 * Ettinger). Not cryptographic: this seeds a walk scheduler, not a security
 * control.
 */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0
  return function next(): number {
    state = (state + 0x6d2b79f5) | 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/**
 * Build a seeded RNG. Two instances constructed with the same seed produce
 * the identical sequence of `next()`/`nextInt()`/`pick()` results, forever;
 * that equality is what makes a walk's seed a replay key.
 */
export function createRng(seed: number = RESOLVED_SEED): SeededRng {
  const next = mulberry32(seed)

  function nextInt(maxExclusive: number): number {
    if (!Number.isInteger(maxExclusive) || maxExclusive <= 0) {
      throw new RangeError(`nextInt requires a positive integer, got ${maxExclusive}`)
    }
    return Math.floor(next() * maxExclusive)
  }

  function pick<T>(items: readonly T[]): T {
    if (items.length === 0) {
      throw new RangeError('pick requires a non-empty array')
    }
    // nextInt(items.length) is always a valid index: 0 <= result < length.
    // No `as T` here: this project has no noUncheckedIndexedAccess, so the
    // indexed access already types as T without an assertion.
    return items[nextInt(items.length)]
  }

  return { seed, next, nextInt, pick }
}
