# Breach Notification Runbook

Status: living document. Owner: Byron Williams (byronawilliams@gmail.com). Last reviewed:
2026-07-20.

This is the internal incident-response procedure required by GDPR Articles 33-34 and referenced
by `docs/compliance/information-security-program.md` Section 5 (remediation plan Phase 6c,
resolving `gdpr-compliance-review.md` finding G-09). It is distinct from `SECURITY.md`'s
external-facing vulnerability-reporting policy: that document tells a *reporter* how to disclose
a vulnerability to us; this document tells *us* what to do once a personal-data breach is
suspected or confirmed, whether it came in through that channel, a processor's own notification,
or internal detection.

## 1. What counts as a "personal data breach" here

GDPR Article 4(12)'s definition governs: "a breach of security leading to the accidental or
unlawful destruction, loss, alteration, unauthorised disclosure of, or access to, personal data
transmitted, stored or otherwise processed." That is broader than "an attacker got in" — it
covers confidentiality breaches (unauthorized access/disclosure), integrity breaches (unauthorized
alteration), and availability breaches (loss of access, including a ransomware event or an
accidental deletion with no backup), and it covers accidental causes (a misconfigured access
control, a bug that leaked another family's data) exactly as much as malicious ones.

Given this app's data model, concrete examples that qualify:

- A vulnerability that exposes one family's child-linked data to another family (an IDOR, an
  authorization-gate bypass).
- A Cloudflare R2, Supabase, or Redis misconfiguration that makes stored data (cover images,
  the Postgres database, the RQ job queue) reachable without authentication.
- A compromised admin or guardian credential used to access data beyond that account's normal
  scope.
- A processor (Supabase, OpenRouter, Cloudflare, Sentry, or any vendor in
  `information-security-program.md` Section 4) notifying us of a breach on their side that
  affected our data.
- Accidental disclosure: a log line, error report, or support interaction that exposes a child's
  identifying data to the wrong party.

**Does not qualify by itself:** a vulnerability finding with no evidence of actual unauthorized
access, alteration, or loss (that is a standard security-fix workflow under `SECURITY.md`,
escalated to this runbook only if evidence of exploitation later emerges).

## 2. Incident-classification rubric

Classify on two axes as soon as an incident is suspected, and re-classify as facts change; do
not wait for a final classification before starting Section 3's escalation.

**Axis A: Confirmed vs. suspected.** A suspected incident (an anomaly, a report with no
corroborating evidence yet) starts the same triage as a confirmed one; the difference is scope of
notification decisions in Section 4, not scope of investigation.

**Axis B: Severity**, driven primarily by whether children's personal data is implicated (this
project's single highest-risk data category) and by scale:

| Severity | Criteria | Example |
|---|---|---|
| **Critical** | Child-linked personal data (a `ChildProfile` row, reading/completion history, a story request's raw text) exposed, altered, or lost across more than one family, OR any exposure enabling unauthorized *write* access to child-linked data | A vulnerability lets any authenticated user enumerate other families' child profiles; an admin credential compromise |
| **High** | Child-linked personal data exposed for a single family/profile, OR guardian/admin account credentials or PII exposed at any scale | An IDOR exposing one family's data to one other family; a leaked Supabase service-role key |
| **Medium** | Non-child personal data exposed (e.g. a guardian's email in a misdirected log), OR availability loss with no confirmed unauthorized access | A backup failure with no evidence of external access; an accidental short-lived R2 bucket misconfiguration caught before evidence of external access |
| **Low** | Near-miss with no data actually exposed, altered, or lost | A dependency CVE with no evidence of exploitation against this deployment |

Severity Critical/High always triggers the Article 33 authority-notification assessment in
Section 4 within the 72-hour clock; Medium/Low are documented and reassessed, not automatically
escalated to notification.

## 3. Escalation path

At the project's current single-maintainer scale, the escalation path is short by necessity; it
is written down anyway so the steps are not improvised mid-incident, and so it has an obvious
place to extend once the team grows.

1. **Detection.** Any of: a `SECURITY.md`-channel report, a monitoring/Sentry alert, a processor
   notification, or a self-discovered anomaly (a code-review finding, an unexpected log pattern).
2. **Triage (target: within 4 hours of detection during business hours, within 24 hours
   otherwise).** The security coordinator (`information-security-program.md` Section 2)
   classifies per Section 2 above, and starts a written incident record (see Section 6) with a
   timestamp for "discovery" — this timestamp is what starts the Article 33 clock in Section 4,
   not the time classification finishes.
3. **Containment.** Stop ongoing exposure first: revoke a compromised credential, roll back a
   bad deploy, take a misconfigured bucket private, disable an affected endpoint. Containment is
   not gated on finishing the investigation.
4. **Investigation.** Determine scope: which data, how many data subjects (and specifically,
   how many are children, since that drives severity and the notification content in Section 5),
   what caused it, whether it is ongoing.
5. **Notification decision (Section 4).**
6. **Remediation and post-incident review.** Fix the root cause, not just the symptom; feed the
   review back into `information-security-program.md` Section 3's risk-assessment cadence per
   its "after any security incident" trigger.

If the team grows beyond a single maintainer, this section is the first thing to update: name
who owns triage vs. containment vs. external communication, so an incident does not default to
one person doing everything under time pressure.

## 4. Notification clocks

Two distinct GDPR duties, tracked separately because meeting one does not satisfy the other:

### Article 33: notifying the supervisory authority (72-hour clock)

- **Trigger:** the breach is "likely to result in a risk to the rights and freedoms of natural
  persons" — for a children's app, assume this threshold is met by default for any Critical or
  High severity incident (Section 2) rather than arguing the exception case under time pressure.
- **Clock starts:** at "awareness" (Article 33(1)) — this runbook treats that as the discovery
  timestamp from Section 3 step 2, not the time investigation completes or classification is
  finalized. A partial, evolving notification within 72 hours is the GDPR-compliant move; waiting
  for complete facts and missing the window is not (Article 33(4) explicitly allows phased
  information "without undue further delay").
- **Recipient:** the relevant EU/UK supervisory authority. **Open item, tracked in the
  remediation plan's consolidated open questions:** which specific authority depends on the
  outcome of Pressure Point P-1 (whether GDPR currently applies to this app's actual user base)
  and the eventual lead-supervisory-authority analysis once that is resolved; this runbook does
  not pre-select one so the placeholder is not mistaken for a resolved decision.
- **Content (Article 33(3)):** nature of the breach, categories and approximate number of data
  subjects and records affected, the security coordinator's contact details, likely consequences,
  and measures taken or proposed to address the breach and mitigate its effects.

### Article 34: notifying affected individuals ("high risk" threshold, no fixed clock but "without undue delay")

- **Trigger:** a higher bar than Article 33 — "likely to result in a *high* risk" to the
  individual. For this app, treat any Critical-severity incident (child-linked data exposed
  across families, or write access compromised) as presumptively meeting this bar; High-severity
  single-family incidents are assessed case by case against Article 34(3)'s exceptions
  (encryption/unintelligibility of the exposed data, subsequent measures ensuring the high risk
  is no longer likely to materialize, or disproportionate effort — the last of which, if relied
  on, requires a public communication instead per Article 34(3)(c), not silence).
- **Recipient:** the guardian of an affected child profile is the notified party — this app has
  no direct channel to a child data subject, consistent with every other guardian-mediated
  interaction in the product (ADR-018's already-decided consent framing).
- **Content:** in clear and plain language, the nature of the breach and, at minimum, the same
  categories of information as Article 33(3) points (b), (c), and (d) above.

### COPPA note

COPPA itself does not impose a federal breach-notification duty comparable to GDPR Articles
33-34; the FTC's expectation under 312.8 is the *security program* preventing breaches (see
`information-security-program.md`), not a breach-notice statute. Several US states impose their
own breach-notification laws (often with shorter clocks or child-specific triggers) that could
apply depending on affected users' state of residence. **Open item:** no state-law analysis has
been performed; if a Critical/High incident occurs, check applicable state breach-notification
law as part of Section 3 step 4 (investigation), not as an afterthought once the GDPR clocks are
already handled.

## 5. Notification content checklist

Whichever clock applies, a notification (to an authority, per Article 33(3), or to a guardian,
per Article 34) should answer, in plain language for the guardian-facing version:

- What happened, and when it was discovered (not necessarily when it started).
- What data was involved — named categories, not "some data" (e.g. "child display name and
  reading history," not "personal information").
- How many data subjects/records are affected, even as an initial estimate.
- What we have already done to contain it.
- What we are doing to prevent recurrence.
- What the recipient (guardian, if Article 34 applies) can do, if anything.
- Who to contact with questions (the security coordinator, Section 2).

## 6. Incident record

Each incident gets a written record from the moment of triage (Section 3 step 2) through
closure, kept alongside this runbook's owner rather than in a public-facing location (it may
contain details about an active vulnerability). At minimum: discovery timestamp, classification
and any reclassification with reasons, containment actions and their timestamps, investigation
findings (scope, cause, affected data subjects), notification decisions made under Section 4 and
their timestamps, and the post-incident remediation items. This record is what
`information-security-program.md` Section 3's post-incident review step operates on.

## 7. Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `SECURITY.md` | External vulnerability-reporting channel; a report there can be the detection trigger for Section 3. |
| `docs/compliance/information-security-program.md` | The broader security program this runbook is Section 5 of; its risk-assessment cadence is fed by this runbook's post-incident review. |
| `docs/compliance/gdpr-compliance-review.md` | Finding G-09, resolved by this document. |
| `docs/compliance/coppa-gdpr-remediation-plan.md` | Phase 6c, whose completion this document is. |
