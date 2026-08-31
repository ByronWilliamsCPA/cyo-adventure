---
title: "Child-owned logins: legal issues review"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Scope the legal consequences of letting a child hold their own login credential instead of
  reading only through a guardian-authorized device, across COPPA, state teen-privacy law, app-store
  accountability statutes, and platform contract rules, and name the decisions and sequencing a
  proposal would need."
tags:
  - planning
  - privacy
  - compliance
  - security
---

# Child-owned logins: legal issues review (2026-08-31)

> **Status**: Draft, decision input only. This document changes no recorded decision and is
> engineering-derived research, not legal advice; the same posture as
> [privacy-model.md](privacy-model.md) and the `docs/compliance/` document set applies.
> **Question asked**: the product was built so that only guardians log in and then hand the device
> to a child (since [ADR-014](adr/adr-014-device-authorized-kid-access.md), hand over a
> device-grant-authorized device). For older kids, parents may want the child to have their own
> login. What legal issues does that change raise?
> **Sourcing convention**: per [ADR-018](adr/adr-018-childrens-privacy-compliance.md)'s Sources
> rule, every external legal claim below is tagged with how it was verified. "Fetched YYYY-MM-DD"
> means the named URL was retrieved and read during this review; a claim without a fetched primary
> source is marked as secondary and must be confirmed before anything is built against it.

## TL;DR

"Their own login" is three different designs wearing one name, and they carry very different legal
weight. A **family-scoped, first-party credential** that a guardian provisions, that carries no
contact information, and that only mints the existing backend child session (Design A below) does
not change which COPPA consent lane the product is in: the KWS verifiable-parental-consent gate
already covers the collection, and what changes is consent *content* (an updated direct notice and
a material-change refresh), the data inventory, the retention schedule, and a real step-up in
breach exposure, because a child username-plus-password pair is itself a breach-notification
trigger under state law. A credential that adds **child-held recovery contact info** (Design B) or
a **third-party identity** (Design C) is a different animal: it collides with COPPA's necessity
limit, permanently forecloses the consent-free free tier ADR-018 D8 is pricing, falsifies factual
premises the counsel engagement brief currently states, contradicts three recorded decisions, and
fights both app platforms' kids rules. The genuinely new law since those decisions were made sits
mostly outside COPPA: New York's Child Data Protection Act binds this product **at any operator
size, today**, and treats a login as the thing that spreads actual knowledge of a minor across
devices; and the app-store accountability statutes (Utah and Texas in force now, Alabama
2026-10-01, California's age-signal law 2027-01-01, Louisiana delayed to 2027-07-01) will hand the
iOS build age-category and parental-consent signals it must consume no matter which login design
is chosen. Recommendation: if the feature is wanted, pursue Design A only, sequence it after the
KWS consent gate is actually on in production, and route the two open legal questions through the
existing counsel and state-law workstreams rather than new ones.

## 1. What is already decided, and what this change would touch

The guardian-only login model is not an accident of implementation; it is recorded, repeatedly, as
a deliberate compliance and security position. A child-login proposal is therefore a **revision of
recorded decisions**, which per house rules happens by amending the ADRs, not by a feature ticket.

| Recorded position | Where | Touched by this change? |
| --- | --- | --- |
| "Children never get IdP identities: a child session is a guardian-authorized profile selection for which the backend mints its own short-lived, single-profile scoped token" | [ADR-008](adr/adr-008-public-app-store-launch.md) decision 2; regulatory constraint "children must not become identifiable accounts in any third-party identity provider" | Design C revises it; Designs A and B do not (the credential stays first-party) |
| "Children never hold third-party identities. Guardians are the only IdP accounts" | [ADR-018](adr/adr-018-childrens-privacy-compliance.md) already-decided item 1 | Same split as above |
| Device grant is "an authorization artifact derived from a Supabase-authenticated guardian, never a competing identity"; kid access is device-anchored | [ADR-014](adr/adr-014-device-authorized-kid-access.md) | Any design revises the device-anchoring model (that is the point of the feature) |
| K16: pick "me" from a picker: "name and avatar, no password or email" | [capability-register.md](capability-register.md) K16 | Any design revises K16's contract (the per-profile PIN already stretches "no password"; a durable credential breaks it) |
| "Almost everything we hold about a child is collected from the guardian, not from the child... a child never holds an email address, a phone number, or a third-party account" | [counsel-engagement-brief.md](../compliance/counsel-engagement-brief.md) Question 1A factual premises | Designs B and C falsify stated facts in a live counsel packet; Design A bends them (see section 7) |
| Child-linked data classification: profile fields are guardian-entered; child-originated data is narrow (wish text, flags, ratings, reading state) | [privacy-model.md](privacy-model.md), [child-origin-dataflow-matrix.md](../compliance/child-origin-dataflow-matrix.md) | Every design adds child-originated rows (the secret the child types, authentication events) |

Also load-bearing context: the product's declared posture is **child-directed** (ADR-018 D2, owner
decision 2026-08-06, mixed-audience defenses recorded as unavailable), launch geography is
**US-only** (D3), and the sole VPC method is **KWS card or debit verification** (D1 owner ruling
2026-08-10), built behind `settings.kws_verification_required`, which is **off in production
today** (`UW-J25`). The six age bands already run to "13-16" and "16+"
([privacy-model.md](privacy-model.md)), so the teen-law exposure discussed below exists before any
login change; a login sharpens it rather than creating it.

## 2. "Their own login" is three designs, not one

The legal analysis diverges immediately on what the credential is, so the designs need names:

- **Design A: guardian-provisioned, family-scoped, first-party credential.** The guardian creates
  (or approves) a username and secret for the child inside the guardian console. The username is
  not contact information and is never shown outside the family; the secret is child-typed. On
  presentation, the backend mints the **existing** child-session token; Supabase never learns the
  child exists, exactly as today. Recovery is guardian-mediated only (guardian resets from the
  console; the child is never asked for an email, phone number, or security questions). Two
  sub-variants matter:
  - **A1, device-bound**: the credential works only on devices that already hold a family device
    grant. The child gets "my own login" independence on the family's devices; nothing else moves.
  - **A2, portable**: the credential also works on a device with no grant (a school tablet, a
    cousin's phone), ideally behind a per-new-device guardian approval loop, which is the model
    the app-store statutes are converging on anyway (minor account affiliated with parent account).
- **Design B: Design A plus child-held recovery contact info** (the child's own email or phone for
  self-service reset), or child self-signup.
- **Design C: the child becomes an identity-provider account**: a Supabase Auth user, possibly via
  "Sign in with Google" or "Sign in with Apple".

"Older kids" needs no age machinery for Design A: COPPA obligations on a child-directed service do
not soften at any age below 13, and nothing in Design A is unlawful for a seven-year-old, so
whether a given child is "old enough for their own login" can stay a **guardian judgment**, exactly
like the existing per-profile PIN. Only a design that wants to treat 13-plus users differently
(self-consent, self-signup, different data rules) needs the product to know ages, and that runs
into the audience-classification wall in section 5.3.

## 3. Federal COPPA analysis (users under 13)

The 2025-amended COPPA Rule (16 CFR Part 312; Federal Register doc.
[2025-05904](https://www.federalregister.gov/d/2025-05904), 90 Fed. Reg. 16918, full compliance
date 2026-04-22, passed) governs everyone under 13, which on the declared child-directed posture
is the presumed audience. ADR-018 carries the detailed rule-text readings; this section only maps
the login change onto them.

### 3.1 What a credential adds to "personal information"

A durable login identifier and its authentication event trail (IP addresses, timestamps) are
persistent identifiers under 16 CFR 312.2, a reading the
[counsel brief](../compliance/counsel-engagement-brief.md) already adopts for the existing child
session. A password is not an enumerated 312.2 element on its own, but once it unlocks a child's
record it sits inside the 312.8 security obligation and, independently, inside state
breach-notification statutes (section 3.5). Design A therefore does not create a **new consent
lane**: the product already owes and gates VPC for child-profile creation
(`api/profiles.py::_require_consent`, the KWS gate), and authenticating a user is an enumerated
"support for the internal operations" purpose. What it creates is **new collection inside an
existing lane**, which drags three obligations with it:

1. **Direct notice and consent refresh.** 16 CFR 312.4(b) and (c) direct notice must describe what
   is collected; 312.5(a)(1) requires consent for material changes to collection practices.
   Adding a child credential to families that consented to the current practices is a material
   change: the direct notice, the retained typed-name consent content (D1's ruling kept it as the
   record of what was agreed), and `policy_version` all need a bump. The mechanics already exist:
   D5's escape-hatch pattern (a `policy_version` bump plus an independent consent surface) was
   priced for exactly this kind of addition.
2. **Data inventory and retention rows before build.** D6's inventory obligation (provenance and
   purpose per element, `UW-A50`) gains rows whose provenance column matters: the secret and every
   authentication event are collected **from the child**, which is the narrow set Question 1A
   turns on. The [data-retention-policy](../compliance/data-retention-policy.md) needs windows for
   credential artifacts and auth logs (312.10 bans indefinite retention and requires a published
   per-class schedule; three classes are already windowless at `UW-N07`, and this must not add a
   fourth).
3. **Collection ordering.** The FTC's clearest account-creation enforcement, *United States v.
   Microsoft Corp.* (Xbox), FTC press release of 2023-06-05 (fetched by this review's research
   pass; URL omitted per ADR-018's ftc.gov convention), turned on collecting a child's signup data
   **before** parental consent, and its order requires deleting pre-consent signup data within two
   weeks. Design A avoids a child-facing signup entirely (the guardian provisions), which is the
   safe shape. If any child-facing enrollment step is ever added, it must collect nothing until
   the family's verification is usable, which the existing gate function
   (`usable_verification_id`) already expresses.

### 3.2 The necessity limit is what rules out Design B

16 CFR 312.7 bars conditioning a child's participation on collecting more personal information
than is reasonably necessary to participate. Self-service recovery contact info fails that test
here, because a guardian-mediated reset path exists by construction (the guardian console). Design
B also collects **online contact information from the child**, a heavier 312.2 category than a
persistent identifier, and none of the 312.5(c) contact exceptions cover holding a child's email
as a standing account attribute. There is no product payoff that justifies opening that front:
recovery through the guardian is the feature working as intended for this audience.

### 3.3 Design C fights the rest of the rule set

A third-party identity puts a child's account, email-or-equivalent, and auth telemetry inside an
IdP (Supabase Auth, and Google or Apple behind it). That is a new disclosure surface for Question
1B's characterisation work, a new processor row with no executed DPA
([processor-dpa-checklist.md](../compliance/processor-dpa-checklist.md) is already the long pole),
and a direct reversal of ADR-008 decision 2 and ADR-018 already-decided item 1. Platform rules
compound it (section 6). Nothing below improves it; this review recommends against Design C
without qualification.

### 3.4 Interaction with the D8 consent-free free tier

ADR-018 D8 prices a free tier under 16 CFR 312.5(c)(7), which requires collecting **"a persistent
identifier and no other personal information."** A Design A credential used only for
authentication and progress sync is the kind of identifier that analysis already assumes (the
counsel brief's 1A section asks about exactly this, with saving reading position as the test
case). Designs B and C collect other personal information by construction (contact info, an IdP
account), so shipping either **forecloses D8 for every family that has one**, before counsel has
even answered whether the tier works (`UW-A52`). This is the cheapest place to lose an option the
owner has repeatedly wanted; it belongs in any decision memo verbatim.

### 3.5 Security program and breach exposure (this is a real step-up)

- **16 CFR 312.8 and D7**: child credentials join the Information Security Program's scope as a
  new high-value class. The engineering patterns exist (`core/pin.py` already stores per-profile
  PINs as PBKDF2; the consent-start endpoint already carries anti-automation caps), but the
  program document and its evidenced cadences must name credential storage, rate limiting,
  lockout-with-guardian-unlock, and enumeration resistance once credentials exist.
- **State breach statutes now reach the kid data.** New York's SHIELD Act defines "private
  information" to include "a user name or e-mail address in combination with a password or
  security question and answer that would permit access to an online account"
  ([N.Y. Gen. Bus. Law § 899-aa(1)(b)(ii)](https://www.nysenate.gov/legislation/laws/GBS/899-AA),
  fetched 2026-08-31); California and most states have equivalents (Cal. Civ. Code § 1798.82,
  cited not fetched). Today a breach of this system exposes no child credential; after this
  change, a credential-table breach is a notifiable event about children in most US states. The
  [breach-notification-runbook](../compliance/breach-notification-runbook.md) needs a
  child-credential scenario before launch, not after.
- **Revocation semantics get guardian-visible.** 16 CFR 312.6(a)(2) gives a parent the right to
  refuse further use and to direct deletion; a credential a guardian cannot suspend, reset, or
  delete from the console would sit badly against it, and consent revocation must actually end
  the child's ability to log in. `UW-A43` (a revoked device grant does not invalidate an
  already-minted 12-hour child session) becomes more load-bearing here: the same no-database-read
  child principal would keep a revoked **credential's** sessions alive too, and the guardian-facing
  copy must not promise otherwise. The `UW-A43` fix (carry a reference in the child-session claims
  and check it on the read path) should be priced into the credential work rather than deferred
  again.

## 4. The teen lane: 13- to 17-year-olds (state law, in force now)

COPPA stops at 13. The bands "13-16" and "16+" exist today, so this lane already binds the
product; a login mostly strengthens the *knowledge* element and adds consent UX obligations if any
non-essential processing rides on it.

### 4.1 New York Child Data Protection Act (the controlling example)

Verified against the statute and the Attorney General's guidance
([N.Y. Gen. Bus. Law § 899-ee](https://www.nysenate.gov/legislation/laws/GBS/899-EE) and
[§ 899-ff](https://www.nysenate.gov/legislation/laws/GBS/899-FF), fetched 2026-08-31;
[OAG Implementation Guidance](https://ag.ny.gov/sites/default/files/2025-05/nycdpa-guidance.pdf),
2025-05-19, fetched and text-extracted 2026-08-31):

- **It binds at any size.** "Operator" carries no revenue or user-count threshold, and the Act has
  been effective since **2025-06-20**. A solo operator with New York minors in a US-only launch is
  covered. This is the concrete instance of the D3 gap the ADR-018 Validation checklist and
  `UW-A53` already name (US-only removes GDPR-K and the UK AADC, not US state law).
- **Coverage**: a "covered user" is a user under 18 who is actually known to be a minor **or** is
  using a service (or portion) "primarily directed to minors." This product is primarily directed
  to minors on any reading, so coverage does not depend on knowledge.
- **Under 13**: § 899-ff(1)(a) adopts COPPA wholesale, so the D1/KWS machinery is also the New
  York answer for that cohort.
- **13 to 17**: processing is lawful only if **strictly necessary** for enumerated purposes or
  with **informed consent given by the teen themselves**, presented separately, with refusal as
  the most prominent option, no dark patterns, and free revocability. Reading assigned books,
  progress sync, and safety moderation sit comfortably inside "providing or maintaining a specific
  product or service requested by the covered user." The guidance's "internal business operations"
  purpose expressly **excludes marketing, advertising, research and development, and providing
  products or services to third parties**, which is a second, state-law reason the D5 corpus
  constraint (no child-originated data in any training or evaluation set) must hold for teens too.
- **The login-specific holding.** The guidance states that once an operator learns a user's age
  and associates it with the account, it has actual knowledge "anywhere the operator can recognize
  the user's account, including when the user logs into the same service or product using
  different devices or accesses different services or products using the same log-in credentials."
  A durable child login is precisely the artifact that makes knowledge portable. That cuts both
  ways: it removes any argument that a session is age-unknown, and it makes the guardian-set age
  band the operative age record, which the product already treats as authoritative.
- **Parent-provisioned services fit the frame.** The guidance recognizes existing frameworks where
  "parents may lawfully agree to a product or service on behalf of or jointly with their child,"
  with strictly-necessary processing for that service permitted without separate teen consent.
  Design A (guardian provisions the credential for a service the guardian subscribed the family
  to) sits inside that frame; teen **self-signup** (Designs B/C) would instead lean on the teen's
  own informed consent with the mandated UX, a heavier and less certain surface.
- **Enforcement**: AG enforcement with rulemaking pending and discretion promised for good-faith
  compliance during the initial period; civil penalties reported at up to $5,000 per violation
  (penalty figure secondary-sourced). No NYCDPA enforcement action against a comparable operator
  was found as of this review.

Practical consequence: Design A adds little new NY exposure **provided nothing non-essential rides
on the login**. The moment a login becomes the key for, say, cross-context personalization or
engagement analytics on teens, § 899-ff consent UX obligations attach.
[ADR-031](adr/adr-031-first-party-friction-beacon.md)'s "the kid surface does not emit, at all"
rule and [ADR-030](adr/adr-030-engagement-correlation-privacy-review.md)'s aggregate-only,
minimum-cohort design are the reason the current posture survives this test; they should be cited
as constraints in any credential ADR so the property is not lost casually.

### 4.2 Other states (thresholds matter, and mostly spare a small operator for now)

Statuses below are as of 2026-08-31; confidence tags follow the research method in section 8.

| Regime | Status | Applies to this operator? |
| --- | --- | --- |
| Colorado SB 24-041 minors duties (eff. 2025-10-01) | In force | Reportedly applies **without** the Colorado Privacy Act's volume thresholds (secondary, medium confidence). If confirmed, duty-of-care and consent duties for under-18s bind now; verify inside `UW-A53` |
| Maryland Kids Code (AADC; eff. 2024-10-01) | In force; motion to dismiss in *NetChoice v. Brown* (D. Md.) denied 2025-11-24, no injunction (secondary, fetched firm summary) | Covered-entity floor: >$25M revenue, or 50k+ consumers, or 50%+ revenue from data sales; out of scope at current scale, and the 50k prong is the one growth crosses first |
| Connecticut SB 3 / SB 1295 minors provisions (amendments eff. 2026-07-01) | In force | General CTDPA threshold now 35k consumers; **whether the minors duties bypass the threshold is unverified** (open gap, `UW-A53`) |
| Nebraska LB 504 (eff. 2026-01-01) | In force | Thresholds verified from the [statute](https://nebraskalegislature.gov/laws/statutes.php?statute=87-1302) (fetched by research pass): >$25M or 50k+ consumers plus majority-online-revenue; out of scope at current scale |
| Vermont AADC (S.69) | Effective 2027-01-01; AG rulemaking under way | Applicability floor unverified against primary text |
| Texas SCOPE Act (HB 18) | Fifth Circuit ruling 2026-07-24 kept monitoring-and-filtering duties enjoined but let the age-registration requirement stand (secondary) | Small-business exemption keyed to SBA size standards (unverified); a "digital service provider" registration duty could reach a login-bearing app with Texas teens; verify inside `UW-A53` |
| Florida HB 3 (social media minors) | Enforceable since an Eleventh Circuit stay of 2025-11-25 (secondary) | Functional scope (feeds, autoplay, addictive-design features, 10%+ under-16 heavy use): a no-feed, no-autoplay assigned-reading app has a strong out-of-scope argument, same shape as the D9 conclusion for California SB 976 |
| California SB 976 / AB 2273 | Unchanged from ADR-018 D9 | D9's "probably out of scope, recorded as open" analysis is not altered by a login |
| Federal: KIDS Act (H.R. 7757) passed the House 267-117 on 2026-06-29 folding in KOSA-minus-duty-of-care and COPPA 2.0 elements; Senate Commerce advanced KOSA (S. 1748) in early August 2026; nothing enacted | Pending | If a COPPA 2.0-style teen tier becomes federal law, the 13-16 lane hardens nationally; horizon item only (congress.gov blocks automated retrieval; bill status secondary-sourced) |

The register row for all of this already exists: `UW-A53` (ADR-018 D9 and the wider US state-law
gap). The teen-login question does not need a new workstream; it needs `UW-A53` to run with New
York and Colorado first on the list.

## 5. App-store accountability statutes (the iOS channel, R2/R3)

These are the newest and least-discussed constraint, and they bind the **distribution channel**
rather than the data practice, so they apply to the iOS build whatever login design is chosen.
They are also content-neutral: the "we are not a social feed" argument that scopes the product out
of SB 976 and Florida HB 3 does nothing here.

### 5.1 Where each statute stands (as of 2026-08-31)

| State | Law | Status |
| --- | --- | --- |
| Utah | App Store Accountability Act (SB 142, amended by HB 498) | Effective 2025-05-07; compliance deadline **2026-05-06 has passed**; AG enforcement stripped by HB 498, private right of action activates 2026-12-31; the CCIA challenge was voluntarily dismissed 2026-04-21 (secondary, fetched firm summaries; [official bill page](https://le.utah.gov/~2025/bills/static/SB0142.html) fetched but carries navigation only) |
| Texas | App Store Accountability Act (SB 2420) | Effective 2026-01-01; preliminarily enjoined 2025-12-23 (W.D. Tex.), stay of the injunction by the Fifth Circuit in May 2026, and the Supreme Court declined to disturb the stay on **2026-07-06**, so the law is **enforceable now** with the merits appeal pending ([SCOTUSblog report](https://www.scotusblog.com/2026/07/supreme-court-allows-texas-to-enforce-law-requiring-age-verification-and-parental-consent-on-app/), fetched 2026-08-31; secondary) |
| Alabama | HB 161 | Effective **2026-10-01**, phase-in to 2027-10-01 for existing accounts; AG-only enforcement (secondary, fetched firm summary) |
| California | AB 1043, Digital Age Assurance Act | Chaptered 2025-10-13; **operative 2027-01-01** (existing accounts by 2027-07-01). Verified against the [bill page](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB1043) (fetched 2026-08-31): OS providers collect age at setup and expose an age-bracket signal (under 13; 13-15; 16-17; 18+); **developers must request the signal at download and first launch, treat it as the primary indicator of age, and not re-collect or share it**; penalties $2,500 to $7,500 per affected child |
| Louisiana | HB 570 (2025), delayed by HB 977 (2026) | Enrolled text verified from the [legislature's document service](https://www.legis.la.gov/legis/ViewDocument.aspx?d=1425304) (fetched 2026-08-31); effective date **delayed to 2027-07-01** (secondary, fetched firm summary of HB 977) |

### 5.2 What the developer-side duties actually are

The Louisiana enrolled text is the clearest statement of the developer half, and Utah and Texas
rhyme with it (La. R.S. 51:1773 as enacted by HB 570, from the fetched enrolled text):

- verify a user's **age category through the app store's data sharing**, and treat store-supplied
  age category data as the floor ("use the lowest age category indicated" when signals conflict);
- if the user is a minor, **confirm verifiable parental consent through the affiliated parent
  account** before the relevant action;
- notify the store of any **significant change** to the app, which triggers renewed parental
  consent for minors;
- request age or consent state at enumerated moments, which expressly include **"at the time a
  user creates a new account with a developer"**;
- never share age category data onward.

That last trigger is this feature: on the iOS channel, creating a child login is itself the event
that obliges the app to pull the store's age category and parental-consent state. Apple's
machinery for all of this is live: the Declared Age Range API on iOS 26+, PermissionKit's
significant-change acknowledgement, and `RESCIND_CONSENT` App Store Server Notifications
([age assurance Q&A](https://developer.apple.com/support/age-assurance), fetched 2026-08-31).
Apple states age categories are shared for new Utah Apple Accounts as of 2026-05-06; its Texas
implementation was **paused** when the injunction issued
([developer news, 2025-12-23](https://developer.apple.com/news/?id=8jzbigf4), fetched 2026-08-31),
and whether that pause has been reversed since the Supreme Court's 2026-07-06 order was not
determinable from Apple's published pages at review time; it must be re-checked before R2.

### 5.3 Design consequences

1. **Parent-affiliated minor accounts are becoming the platform default.** Every one of these
   statutes builds the same shape: a minor's account is linked to a parent account, and consent
   flows through that link. Design A is the in-app mirror of that shape; Design C would create a
   *second*, unlinked identity fighting it.
2. **The web and iOS channels will diverge.** The web PWA receives no OS age signal and none of
   these statutes reach it; the iOS build must request and honor signals. The credential model
   should be designed so the iOS channel can overlay store-supplied age category and consent
   state on the same first-party credential, rather than baking a per-channel identity.
3. **A fourth age taxonomy arrives.** The product's six bands, COPPA's under-13 line, the
   CA/TX-style brackets (under 13; 13-15; 16-17), and Apple's Kids Category bands (5 and under;
   6-8; 9-11) do not align. The age-band model needs a mapping layer, decided once, rather than
   ad hoc conversions in the client.
4. **Timeline pressure is real but not immediate**: nothing binds the current web-only R1 tier;
   Utah and Texas bind the moment an iOS build ships to those storefronts; Alabama adds
   2026-10-01; California's signal-request duty lands 2027-01-01. ADR-008's Phase 7 checklist is
   the natural home for a per-state gating row.

## 6. Platform contract rules (bind on distribution, whatever the law says)

- **Kids Category tops out at 11.** Apple's [Kids apps page](https://developer.apple.com/app-store/kids-apps/)
  (fetched 2026-08-31) defines the category's bands as 5 and under, 6-8, and 9-11. An "older kids
  with their own login" story aimed at 10-15 straddles the category boundary; that is an ADR-008
  audience-and-listing question (D2 declared child-directed and Kids Category), and any teen-lane
  product design would reopen it. Note the asymmetry: adding Design A for under-12s fits the
  category; marketing a teen tier does not.
- **Guideline 5.1.4** (App Review Guidelines, fetched by the research pass 2026-08-31): kids-app
  birthdate or parental-contact collection is allowed "only for the purpose of complying with
  these statutes," and, quoted because it is routinely misread, "the parental gate requirement for
  the Kid's Category is generally **not** the same as securing parental consent to collect
  personal data under these privacy statutes." Design B's recovery email would be collection 5.1.4
  frowns on; Design A collects neither birthdate nor contact info.
- **Kids apps must not transmit PII to third parties without parental consent** (same Kids page).
  Design C's OAuth handshakes send child data to the IdP by construction.
- **Guideline 4.8 (login services)**: Sign in with Apple (or an equivalent privacy-preserving
  login) is required **only when the app offers a third-party or social login**; an app that
  "exclusively uses your company's own account setup and sign-in systems" is exempt (fetched by
  the research pass). Design A never triggers 4.8; Design C does, and then owes Sign in with Apple
  alongside Google.
- **Google Play (the later Android channel)**: the
  [Families policy](https://support.google.com/googleplay/android-developer/answer/9893335)
  (fetched by the research pass) bars child-directed apps from containing "any APIs or SDKs that
  are not approved for use in primarily child-directed services," which is the practical block on
  embedding a general-purpose Sign in with Google SDK in a kids app. Family Link supervised
  accounts **can** grant third-party access under parental controls
  ([Google support page](https://support.google.com/families/answer/9204736), fetched by the
  research pass), so the folk claim that supervised accounts cannot OAuth at all is not supported;
  what is true is that the path is parent-gated, per-app, and revocable, meaning Design C on
  Android would be high-friction and SDK-constrained rather than impossible.
- **FTC posture on age screens**: a 2026-02-25 FTC policy statement (fetched by the research pass;
  URL omitted per the ftc.gov convention) forbears from COPPA enforcement over data collected
  **solely** to determine age, under conditions (use limited to age determination, prompt
  deletion, security, notice). Relevant only if a future design adds an age-screen step; Design A
  does not need one.

## 7. Interaction with the open compliance workstreams (sequencing)

| Open item | Interaction |
| --- | --- |
| D1 / `O-123` / `O-125` / `UW-J25`: KWS is the sole VPC method, the gate flag is off in production, the first real send is gated on the Epic processor disclosure, and the mechanism is unexercised on a tier serving real families | **Precondition.** Shipping new child-data collection to families whose consent evidence is the typed-name record D1 declined to rely on would grow the Question 1A installed-base problem on purpose. Child credentials should ship only to families holding a usable KWS verification, which in practice means after the production switch-on |
| Counsel engagement (`UW-M03`, Questions 1A and 1B) | The brief states as fact that a child "never holds an email address, a phone number, or a third-party account" and that child-originated data is narrow. Design A changes the narrow set (adds a child-typed secret and auth events); B and C falsify the sentence outright. **Do not ship any design while the packet is live without updating Section 1's facts**, and if the feature is pursued, add the credential as a rider on Question 1A (the same way D8 rides on 1A) rather than as a sixth question |
| D6 data inventory (`UW-A50`) | Credential and auth-event rows, provenance "from the child," purpose "authentication," before build |
| D8 free tier (`UW-A52`) | Design A is compatible with the 312.5(c)(7) analysis; B and C foreclose it per family. Any credential ADR must state this dependency |
| D9 and state law (`UW-A53`) | NY CDPA and Colorado move to the front of that row's queue; the app-store statutes add the R2 gating table in section 5.1 |
| K16 (capability register) and ADR-014 | Both need amendment text in the proposal; ADR-014's device grant remains the web-channel anchor under A1 |
| `UW-A43` (revoked grant does not end a live child session) | Extend the fix to credentials in the same change; guardian-facing copy must state the session tail honestly |
| ADR-030 / ADR-031 analytics constraints | Cite as standing constraints in the credential ADR so no teen-scoped, login-keyed analytics ride along and trip § 899-ff |

## 8. Recommendation

1. **If the feature is wanted, build Design A1** (guardian-provisioned first-party credential on
   already-authorized devices), then A2 (portability behind per-new-device guardian approval)
   once the app-store signal work exists anyway. Do not build B. Do not build C.
2. **Sequence after the KWS production switch-on**, and only for verified families.
3. **Run the paperwork with the build, not after it**: direct-notice and `policy_version` refresh,
   D6 inventory rows, retention windows, breach-runbook scenario, ISP update, K16 and ADR-014
   amendments, counsel-brief fact update plus the 1A rider.
4. **Fold the teen-lane scoping into `UW-A53`** with New York and Colorado first; no new
   workstream.
5. **Add an R2 gate row for app-store accountability** (Utah and Texas now, Alabama 2026-10-01,
   California 2027-01-01, Louisiana 2027-07-01), including re-checking Apple's Texas rollout
   status after the 2026-07-06 Supreme Court order.

**Decision needed** (owner): whether child-owned logins are pursued at all, and if so, that Design
A is the chosen shape and the sequencing above is accepted. That ruling is the trigger for the
ADR-014/ADR-018/K16 amendment work; nothing in this document performs it.

## 9. Follow-on work

Per the register's linkage contract, the decision this review directs is recorded at **`UW-A59`**
in the [unscheduled work register](unscheduled-work-register.md) (Cluster A), status `decision`,
Phase 7, added by the same change that adds this document. `UW-A53` (state-law scoping) and
`UW-A52` (D8 exception scope) carry the two dependencies this review leans on hardest.

## 10. Sources and references

House rule (ADR-018): a claim sourced from the primary column can be relied on here; a claim from
the secondary column is a lead with provenance attached. URLs appear only where the page was
actually fetched during this review (2026-08-31, by this review directly or by its research pass);
FTC and congress.gov materials are named without URLs because those hosts block automated
retrieval from this environment (the same convention ADR-018 adopted).

### Primary sources (fetched)

| Source | Authoritative for |
| --- | --- |
| [N.Y. Gen. Bus. Law § 899-ee](https://www.nysenate.gov/legislation/laws/GBS/899-EE), [§ 899-ff](https://www.nysenate.gov/legislation/laws/GBS/899-FF), [§ 899-aa](https://www.nysenate.gov/legislation/laws/GBS/899-AA) | NYCDPA definitions and processing rules; SHIELD Act "private information" including username-plus-password |
| [NY OAG, NYCDPA Implementation Guidance (2025-05-19)](https://ag.ny.gov/sites/default/files/2025-05/nycdpa-guidance.pdf) | COPPA adoption for under-13s; strictly-necessary readings; account-recognition actual-knowledge language; parent-provisioned-service frame; enforcement discretion |
| [California AB 1043 bill page (chaptered)](https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202520260AB1043) | Age-bracket signal duties on OS providers and developers; operative dates; penalties |
| [Louisiana HB 570, enrolled text](https://www.legis.la.gov/legis/ViewDocument.aspx?d=1425304) | Developer-side duties including the account-creation trigger and lowest-age-category rule |
| [Neb. Rev. Stat. § 87-1302](https://nebraskalegislature.gov/laws/statutes.php?statute=87-1302) | Nebraska applicability thresholds |
| [Apple: Kids apps](https://developer.apple.com/app-store/kids-apps/), [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), [age assurance Q&A](https://developer.apple.com/support/age-assurance), [developer news 2025-12-23](https://developer.apple.com/news/?id=8jzbigf4) | Kids Category bands and rules; 5.1.4 and 4.8 text; Declared Age Range API and consent-revocation mechanics; Texas pause. Contractual, not legal, authority |
| [Google Play Families policy](https://support.google.com/googleplay/android-developer/answer/9893335), [Family Link third-party access](https://support.google.com/families/answer/9204736) | SDK restrictions in child-directed apps; supervised-account third-party access is parent-gated, not absent |
| [Utah SB 142 bill page](https://le.utah.gov/~2025/bills/static/SB0142.html) | Bill identity only; the fetched page is a navigation shell, so Utah substantive claims rest on the secondary column |
| FTC: *US v. Microsoft* (Xbox) press release, 2023-06-05; FTC COPPA age-verification policy statement, 2026-02-25 (fetched; URLs omitted per the ftc.gov convention) | Account-creation ordering enforcement and the two-week pre-consent deletion remedy; age-screen forbearance conditions |
| [Federal Register doc. 2025-05904](https://www.federalregister.gov/d/2025-05904) | The amended COPPA Rule (citation carried from ADR-018; substance re-confirmation remains on ADR-018's validation checklist) |

### Secondary sources (leads, not authority)

- [SCOTUSblog on the 2026-07-06 order](https://www.scotusblog.com/2026/07/supreme-court-allows-texas-to-enforce-law-requiring-age-verification-and-parental-consent-on-app/):
  Texas SB 2420 enforceable pending the Fifth Circuit merits appeal.
- [Stoel Rives on Utah SB 142/HB 498](https://www.stoel.com/insights/publications/utahs-app-store-accountability-act-goes-into-effect)
  and [Reed Smith on Texas SB 2420](https://www.reedsmith.com/our-insights/blogs/viewpoints/102kddh/texas-law-requires-age-verification-for-app-stores-and-developers/):
  duty structure and dates where the bill PDFs would not parse.
- [Alston & Bird on Louisiana's HB 977 delay](https://www.alstonprivacy.com/louisiana-delays-app-store-accountability-effective-date-to-july-2027/)
  and [Regulatory Oversight on Alabama HB 161](https://www.regulatoryoversight.com/2026/03/alabama-enacts-app-store-accountability-act-requiring-age-verification-and-parental-consent/).
- [Troutman on the Maryland Kids Code motion-to-dismiss denial](https://www.troutmanprivacy.com/2025/11/district-court-denies-motion-to-dismiss-challenge-to-marylands-kids-code/).
- KIDS Act (H.R. 7757), KOSA (S. 1748), COPPA 2.0 (S. 836): named only; congress.gov blocks
  automated retrieval, so chamber-status claims above are press-corroborated but unverified
  against the record. A claim that COPPA 2.0 passed a Senate floor vote in March 2026 was found
  and could **not** be verified; it is deliberately not repeated in the body of this review.
- Colorado SB 24-041 threshold-free minors duties; Texas SCOPE Act small-business exemption;
  Florida HB 3 and Texas SCOPE litigation timelines; Maryland and Vermont applicability floors:
  all carried at medium confidence pending `UW-A53` verification against primary text.
