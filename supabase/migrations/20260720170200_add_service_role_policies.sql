-- ADR-021: explicit allow-all RLS policies for the service roles on every
-- table where 20260711200745_enable_rls_all_tables.sql enabled RLS. This is
-- the act-on-the-#VERIFY step that migration's #CRITICAL comment demanded
-- before any non-owner role connects. USING (true) WITH CHECK (true) is
-- deliberate: the application owns authorization (ADR-009 decision point 7);
-- RLS here is a named role boundary, not row-level tenancy. anon and
-- authenticated get NO policies: their deny-by-default posture is unchanged.
--
-- DROP POLICY IF EXISTS + CREATE POLICY keeps re-application idempotent with
-- no down-migration (ADR-012 forward-only). Must run after
-- ..._create_service_roles.sql (CREATE POLICY ... TO <role> errors on a
-- missing role); the timestamps enforce that ordering.
--
-- Table list matches the GRANT block in ..._create_service_roles.sql: the
-- 19 tables from 20260711200745_enable_rls_all_tables.sql plus device_grant,
-- family_connection, and kid_flag, which later migrations independently
-- enabled RLS on with the same deny-by-default posture (see that file's
-- comments for the introducing migration of each).

DROP POLICY IF EXISTS service_rw ON public.child_profile;
CREATE POLICY service_rw ON public.child_profile
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.completion;
CREATE POLICY service_rw ON public.completion
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.concept;
CREATE POLICY service_rw ON public.concept
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.device_grant;
CREATE POLICY service_rw ON public.device_grant
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.family;
CREATE POLICY service_rw ON public.family
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.family_connection;
CREATE POLICY service_rw ON public.family_connection
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.generation_job;
CREATE POLICY service_rw ON public.generation_job
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.kid_flag;
CREATE POLICY service_rw ON public.kid_flag
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.moderation_setting;
CREATE POLICY service_rw ON public.moderation_setting
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.moderation_threshold;
CREATE POLICY service_rw ON public.moderation_threshold
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.moderation_threshold_audit;
CREATE POLICY service_rw ON public.moderation_threshold_audit
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.pipeline_event;
CREATE POLICY service_rw ON public.pipeline_event
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.provider_model_allowlist;
CREATE POLICY service_rw ON public.provider_model_allowlist
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.provider_model_allowlist_audit;
CREATE POLICY service_rw ON public.provider_model_allowlist_audit
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.rating;
CREATE POLICY service_rw ON public.rating
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.reading_state;
CREATE POLICY service_rw ON public.reading_state
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.series;
CREATE POLICY service_rw ON public.series
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.story_request;
CREATE POLICY service_rw ON public.story_request
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.storybook;
CREATE POLICY service_rw ON public.storybook
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.storybook_assignment;
CREATE POLICY service_rw ON public.storybook_assignment
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.storybook_version;
CREATE POLICY service_rw ON public.storybook_version
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public."user";
CREATE POLICY service_rw ON public."user"
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);
