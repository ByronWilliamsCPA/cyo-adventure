-- ADR-018 D1 follow-up: give a failed OUTBOUND send its own terminal status.
--
-- Before this, a send that raised left the row in `sent`. That is the honest
-- reading of "unresolved", but it is also the state the resend guard treats as an
-- email in flight (consent/service.py::open_attempt_started_at), so a guardian whose
-- send failed outright was locked out of retrying for the full cooldown on account of
-- an email that never left. The row now resolves to `send_failed` instead, which the
-- resend guard does not see.
--
-- `send_failed` is deliberately NOT `failed`. `failed` is KWS's answer about a parent,
-- arriving over the inbound leg: this adult was not verified. `send_failed` is our own
-- outbound call giving up and says nothing whatever about the parent. Collapsing them
-- would write a false negative about an adult nobody ever asked, and would tell the
-- delivery-health alarm that the return path works when only our timeout handler ran.
--
-- No data migration accompanies this. Existing rows keep their current status, and any
-- row left `sent` by an old send failure stays `sent`: it is genuinely unknown whether
-- that email went out, and inventing `send_failed` for it retroactively would assert
-- something this system never observed.
--
-- ck_kws_verification_resolution_pairing is unchanged and still reads
-- "(status = 'sent') = (resolved_at IS NULL)", so a `send_failed` row must carry a
-- resolved_at. That is why the ORM-side reader of "a delivery arrived" filters on
-- status rather than on resolved_at alone.

ALTER TABLE "public"."kws_verification"
    DROP CONSTRAINT IF EXISTS "ck_kws_verification_status";

ALTER TABLE "public"."kws_verification"
    ADD CONSTRAINT "ck_kws_verification_status"
    CHECK (status IN ('sent', 'verified', 'failed', 'send_failed'));

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
