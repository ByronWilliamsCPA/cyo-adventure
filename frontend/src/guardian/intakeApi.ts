/**
 * Adapter + pure helpers for the guardian concept-intake surface (C4a-5).
 *
 * Hand-typed like profilesApi.ts: the generated client in src/client/ is not
 * committed. Types mirror ConceptBrief (generation/concept.py) and the
 * generation endpoints in api/generation.py. buildBrief and statusPill are
 * pure so they can be unit-tested without React.
 */

import type { AxiosInstance } from 'axios'

import type { AgeBandValue } from '../profiles/profilesApi'

export type ToneValue = 'gentle' | 'adventurous' | 'silly'

/** Tone chip choices from wireframe 4.5 (Gentle / Adventurous / Silly). */
export const TONES: { value: ToneValue; label: string }[] = [
  { value: 'gentle', label: 'Gentle' },
  { value: 'adventurous', label: 'Adventurous' },
  { value: 'silly', label: 'Silly' },
]

export type JobStatus = 'queued' | 'running' | 'passed' | 'needs_review' | 'failed'
export type StorybookStatus = 'draft' | 'in_review' | 'needs_revision' | 'published' | 'archived'

export interface Protagonist {
  name: string
  age: number
  role: string
}

export interface ConceptBriefBody {
  title: string | null
  premise: string
  protagonist: Protagonist
  point_of_view: string
  age_band: AgeBandValue
  reading_level_target: number
  tier: number
  tone: string
  themes_allowed: string[]
  content_nogo: string[]
  target_node_count: number
  ending_count: number
  structure_pattern: string
  desired_variables: string[]
  special_constraints: string[]
}

export interface GenerationJobSummary {
  id: string
  status: JobStatus
  storybook_id: string | null
  storybook_status: StorybookStatus | null
  version: number | null
  error: string | null
  title: string | null
  premise_snippet: string
  age_band: string | null
  created_at: string
}

export type StatusPill = 'Generating' | 'Waiting for review' | 'Approved' | 'Archived' | 'Failed'

// Per-band defaults. nodes/endings come from validator/band_profile.py
// _PROFILES (min_nodes / min_endings); protagonistAge is the band lower bound.
// #ASSUME: data-integrity: fkTarget mirrors band_profile.py's _READING_LEVEL_TARGET (the source of record;
// FK targets mirror validator/band_profile.py's _READING_LEVEL_TARGET, the
// single source of record (owner ruling 2026-08-18). They used to be
// independently "proposed defaults" and drifted from what the validator grades
// against: 4.0 vs 4.5 at 8-11, 6.0 vs 5.5 at 10-13, 8.0/10.0 vs 7.0/9.0 at the
// teen bands (`UW-C281`). Used only when reading_level_cap is the unset 99
// sentinel.
// #VERIFY: test_reading_level_sources.py::test_frontend_band_defaults_match_the_source_table
// parses this literal and compares it to the Python table.
const BAND_DEFAULTS: Record<
  AgeBandValue,
  { nodes: number; endings: number; protagonistAge: number; fkTarget: number }
> = {
  '3-5': { nodes: 8, endings: 2, protagonistAge: 3, fkTarget: 1 },
  '5-8': { nodes: 12, endings: 2, protagonistAge: 5, fkTarget: 2.5 },
  '8-11': { nodes: 15, endings: 3, protagonistAge: 8, fkTarget: 4.5 },
  '10-13': { nodes: 25, endings: 3, protagonistAge: 10, fkTarget: 5.5 },
  '13-16': { nodes: 30, endings: 4, protagonistAge: 13, fkTarget: 7 },
  '16+': { nodes: 30, endings: 4, protagonistAge: 16, fkTarget: 9 },
}

// reading_level_cap defaults to 99.0 server-side (an unset ceiling, not a
// target); at or above this sentinel the band-default FK target applies.
const READING_CAP_SENTINEL = 99

/** Default fictional protagonist name; NEVER a real child's display name. */
export const DEFAULT_PROTAGONIST_NAME = 'Explorer'
const DEFAULT_PROTAGONIST_ROLE = 'a curious young adventurer'

export interface BuildBriefParams {
  premise: string
  tone: ToneValue
  ageBand: AgeBandValue
  /**
   * The selected child's reading_level_cap. Below the 99 sentinel it is used
   * as the FK target directly; at/above it the band-default fkTarget applies.
   */
  readingLevelCap: number
  /** Optional guardian-supplied fictional name; falls back to the generic default. */
  protagonistName?: string
  /**
   * Present only so tests can prove it is never used. buildBrief must not read
   * this into any brief field: the server screens the brief against real child
   * names and the display name must never enter the prompt.
   */
  childDisplayName?: string
  /**
   * G2: the selected child's profilesApi.ts ProfileView.banned_themes,
   * carried into the brief's content_nogo verbatim (mirrors the same
   * derivation server-side for the child-initiated flow, see
   * story_requests/brief.py::_content_controls). Defaults to no exclusions
   * when omitted, matching the pre-G2 behavior.
   */
  bannedThemes?: string[]
}

/**
 * Assemble a full ConceptBrief from the form inputs plus explicit repo-derived
 * defaults. Every required ConceptBrief field is set here.
 *
 * #CRITICAL security/PII: no field is derived from childDisplayName; the
 * protagonist name is a generic fictional default unless the guardian typed a
 * fictional override.
 */
export function buildBrief(params: BuildBriefParams): ConceptBriefBody {
  const band = BAND_DEFAULTS[params.ageBand]
  const name = params.protagonistName?.trim() || DEFAULT_PROTAGONIST_NAME
  const readingLevelTarget =
    params.readingLevelCap < READING_CAP_SENTINEL
      ? // A cap is a CEILING (api/schemas.py: "can only ever tighten") and the
        // validator reads a target as the CENTRE of a plus-or-minus window, so
        // substituting it let a cap ABOVE the band target silently raise it.
        // Clamping matches band_profile.clamp_target_to_cap (`UW-C281`).
        Math.min(band.fkTarget, params.readingLevelCap)
      : band.fkTarget
  return {
    title: null,
    premise: params.premise,
    protagonist: {
      name,
      age: band.protagonistAge,
      role: DEFAULT_PROTAGONIST_ROLE,
    },
    point_of_view: 'second',
    age_band: params.ageBand,
    reading_level_target: readingLevelTarget,
    tier: 1,
    tone: params.tone,
    themes_allowed: [],
    // G2: the selected child's banned_themes, or none when unset/omitted.
    content_nogo: params.bannedThemes ?? [],
    target_node_count: band.nodes,
    ending_count: band.endings,
    structure_pattern: 'branch_and_bottleneck',
    desired_variables: [],
    special_constraints: [],
  }
}

/**
 * Map a job + its linked storybook to a display pill (see the plan's pill
 * mapping table). A needs_review job WITHOUT a storybook is a gate-failed
 * request and reads "Failed"; needs_review WITH a storybook (future shape)
 * stays "Waiting for review". A published-then-pulled storybook is `archived`,
 * a terminal state, so it reads "Archived" rather than falling through to the
 * misleading "Waiting for review" default.
 */
export function statusPill(job: {
  status: JobStatus
  storybook_id: string | null
  storybook_status: StorybookStatus | null
}): StatusPill {
  if (job.status === 'queued' || job.status === 'running') return 'Generating'
  if (job.storybook_status === 'published') return 'Approved'
  if (job.storybook_status === 'archived') return 'Archived'
  if (job.status === 'failed') return 'Failed'
  if (job.status === 'needs_review' && job.storybook_id === null) return 'Failed'
  return 'Waiting for review'
}

/**
 * Coarse relative age of an ISO timestamp for the "Requested ..." line under
 * each request row: "just now", "4 minutes ago", "2 hours ago", "3 days ago".
 * Minutes/hours/days granularity only; the caller re-renders on each poll
 * tick, which keeps active rows fresh without a dedicated timer.
 *
 * Returns null for an unparseable timestamp so callers can skip the line.
 *
 * #EDGE: timing-dependencies: the client clock can sit behind the server
 * clock that stamped created_at, yielding a "future" timestamp.
 * #VERIFY: negative elapsed time clamps to "just now"; intakeApi.test.ts
 * future-timestamp case.
 */
export function formatRelativeTime(iso: string, nowMs: number): string | null {
  const thenMs = Date.parse(iso)
  if (Number.isNaN(thenMs)) return null
  const elapsedMs = Math.max(0, nowMs - thenMs)
  const minutes = Math.floor(elapsedMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return hours === 1 ? '1 hour ago' : `${hours} hours ago`
  const days = Math.floor(hours / 24)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

export interface ConceptCreated {
  concept_id: string
}

export interface GenerationEnqueued {
  job_id: string
  status: 'queued'
}

export interface IntakeApi {
  createConcept(brief: ConceptBriefBody): Promise<ConceptCreated>
  generate(conceptId: string): Promise<GenerationEnqueued>
  listJobs(): Promise<GenerationJobSummary[]>
}

export function makeIntakeApi(api: AxiosInstance): IntakeApi {
  return {
    async createConcept(brief: ConceptBriefBody): Promise<ConceptCreated> {
      const res = await api.post<ConceptCreated>('/v1/concepts', { brief })
      return res.data
    },
    async generate(conceptId: string): Promise<GenerationEnqueued> {
      const res = await api.post<GenerationEnqueued>(`/v1/concepts/${conceptId}/generate`)
      return res.data
    },
    async listJobs(): Promise<GenerationJobSummary[]> {
      const res = await api.get<{ jobs: GenerationJobSummary[] }>('/v1/generation-jobs')
      return res.data.jobs
    },
  }
}
