-- W0.4 follow-up: backfill "resulting_storybook_id" for requests whose
-- storybook was published BEFORE that column existed.
--
-- Why this is required rather than optional. 20260801000000_add_story_request_
-- resulting_storybook_id.sql adds the column as NULL and
-- publishing/service.py::approve() stamps it going forward only, so every book
-- already on a shelf keeps a NULL. In the same change RequestStory.tsx retired
-- isLikelyPublished (a substring match of the request text against shelf
-- titles) in favour of isPublishedToShelf, which requires a non-NULL
-- resulting_storybook_id. Without a backfill the swap is a regression, not a
-- neutral improvement: every already-published request card reads "your story
-- is being written!" permanently, for books the child can see on the shelf
-- directly beneath it. That directly contradicts capability-register K12 ("a
-- child can tell that the story they asked for has arrived") and is exactly
-- the confusing state the heuristic existed to avoid.
--
-- The resolution mirrors _stamp_resulting_storybook_id's two hops
-- (storybook -> generation_job on (storybook_id, version) -> concept_id ->
-- story_request on concept_id) rather than inventing a third way to walk the
-- chain, so a row backfilled here is indistinguishable from one stamped at
-- publish time.
--
-- Deliberately conservative in three ways, because a WRONG link is worse than
-- a missing one: it would tell a child their request produced a book that in
-- fact belongs to a different request.
--
--   1. Published books only ("status" = 'published' with a non-NULL
--      "current_published_version"). A draft or in-review storybook must never
--      become visible to a child through this field, which is the same reason
--      approve() is its sole writer.
--   2. Only unambiguous resolutions. Neither (generation_job.storybook_id,
--      version) nor story_request.concept_id carries a unique constraint (the
--      gap _stamp_resulting_storybook_id documents in its own #ASSUME), so a
--      concept that resolves to more than one published storybook is SKIPPED
--      by the HAVING clause rather than guessed at. Those requests keep their
--      NULL and keep reading "being written", the same conservative failure
--      the runtime path chooses when its scalar_one_or_none finds nothing.
--   3. Never overwrites. "resulting_storybook_id" IS NULL in the WHERE means a
--      value already stamped by approve() wins, which also makes this
--      migration re-runnable as a no-op (forward-only per ADR-012; no down
--      script).
--
-- Requests that legitimately have no originating link (guardian-authored or
-- catalog books, whose generation job has no request row) are untouched, and
-- correctly so: they were never surfaced on a kid request card in the first
-- place.

UPDATE "public"."story_request" AS sr
SET "resulting_storybook_id" = resolved."storybook_id"
FROM (
    SELECT
        gj."concept_id" AS "concept_id",
        min(sb."id") AS "storybook_id"
    FROM "public"."storybook" AS sb
    JOIN "public"."generation_job" AS gj
        ON gj."storybook_id" = sb."id"
        AND gj."version" = sb."current_published_version"
    WHERE sb."status" = 'published'
        AND sb."current_published_version" IS NOT NULL
    GROUP BY gj."concept_id"
    HAVING count(DISTINCT sb."id") = 1
) AS resolved
WHERE sr."concept_id" = resolved."concept_id"
    AND sr."resulting_storybook_id" IS NULL;
