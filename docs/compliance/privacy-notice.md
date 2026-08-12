---
title: "Privacy Notice (Draft for Counsel Review)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Guardian-facing privacy notice drafted for counsel review, synthesized from the shipped consent/data-handling implementation and the Records of Processing Activities."
tags:
  - compliance
  - privacy
  - legal
component: Development-Tools
source: "Deliverable for coppa-gdpr-remediation-plan.md Phase 2c, synthesized from records-of-processing-activities.md; draft version 2026-07-20."
---

**Status: DRAFT.** Written for counsel to review and redline, not yet published. This is
the deliverable for `coppa-gdpr-remediation-plan.md` Phase 2c, synthesized from the actual
shipped consent/data-handling implementation (Phase 2a, Phase 3, Phase 4d, Phase 6) and the
Records of Processing Activities (`records-of-processing-activities.md`) rather than written
in the abstract. Once approved, this becomes the guardian-facing page linked from the landing
page, the guardian console, and the `GuardianConsentPage` consent-capture screen (Phase 2c's
remaining "link it" step). Everything below is guardian-facing language; the version stamp
below must match `frontend/src/auth/onboardingApi.ts`'s `CONSENT_POLICY_VERSION` once
published, so a recorded consent (`User.consent_policy_version`) always points at the exact
text a guardian agreed to.

**Draft version: 2026-07-20** (matches `CONSENT_POLICY_VERSION` as of this writing).

---

## CYO Adventure Privacy Notice

*Last updated: [DATE OF PUBLICATION]*

### Who we are

CYO Adventure ("we," "us") operates a choose-your-own-adventure reading app for kids. The
person responsible for your and your child's information (the "controller," in EU/UK privacy
terms) is [CONTROLLER LEGAL NAME/ENTITY — currently Byron Williams; confirm whether a formal
business entity should be named here before publication]. Contact: byronawilliams@gmail.com.

### Who this notice covers

This notice is written for **guardians** (parents and legal guardians who create and manage
accounts) and describes what we collect about you and about the children whose profiles you
create. Children do not create their own accounts, provide their own consent, or receive
marketing of any kind; every child-linked interaction happens inside a profile a guardian
sets up and controls.

### What we collect and why

| What | About whom | Why (purpose) | Legal basis (see Note 1) |
|---|---|---|---|
| Email, authentication identity, account role | Guardian | Operate your account, let you sign in | Contract |
| Consent record (your typed name, the date, and the policy version you agreed to) | Guardian | Prove verifiable parental consent under COPPA and GDPR Article 8 | Legal obligation |
| Adult-check record (a reference number, the country you selected, when we asked, and whether the check came back confirmed, refused, or was never answered) | Guardian | Establish through an independent service that the person setting up child profiles is an adult | Legal obligation |
| Country of residence, chosen from a list on the same screen where you give consent | Guardian | Determine which country's privacy and online-safety rules apply to your account (for example GDPR in the EU/EEA, the Online Safety Act in the UK, COPPA in the US) | Legitimate interest (see Note 1) |
| Confirmation that you are an adult, and the date you confirmed it | Guardian | Determine which age-related regulations apply to your account. This is a self-declaration: we record the date you checked the box, not proof of your age or identity | Legitimate interest (see Note 1) |
| Child's display name (a nickname, not a legal name), age band, reading-level cap, avatar (from a fixed set of illustrations, not a photo), content settings | Child | Build and safely tailor your child's reading profile | Contract, on your behalf as their guardian |
| Story requests (your child's or your own typed story ideas), reading progress, completions, ratings | Child | Generate, moderate, and deliver stories; let your child pick up where they left off | Contract |
| Cross-family connection settings, if you choose to link with another family | Guardian | Let book recommendations flow between families you've explicitly agreed to connect with | Consent (a separate, explicit "Allow" click for the connection itself; see below) |
| Admin actions on your account or your child's profiles, and admin *views* of your family's data across families | Guardian, Child | Safety review, account support, and an audit trail of who did what | Legal obligation / legitimate interest (accountability) |

**About the country and adulthood fields**: we do not verify the country you select, and we do
not check any identification to confirm you are an adult. We record what you tell us, the
country you choose and the date you checked the box, and nothing more.

**Note 1**: We have not yet formally documented an Article 6 basis for every purpose above in
a way that has been reviewed by counsel; the table states our best current understanding.
[COUNSEL: please confirm or correct each basis before publication.]

**What we deliberately do not collect from a child**: your child's real name, birthdate,
exact age, photo, email address, phone number, or location. Your child never has their own
email/phone/OAuth identity — every login path (a picker PIN, a guardian-authorized device, or
a guardian-minted session) resolves back to your account.

### How we get your permission (verifiable parental consent)

Before you can create a child profile, we ask you to type your full legal name and check a
box confirming that you are that child's parent or legal guardian and that you agree to this
notice. We record your typed name, the date, the version of this notice you agreed to, and
your IP address at the time, alongside the sign-in you already completed. [NOT A COUNSEL ASK, as
of 2026-08-09. This mechanism was flagged in ADR-018 D1 as needing review; the owner ruled that
the approach as built meets the requirement and withdrew the question from the engagement. It is
carried as an accepted exception at assurance-register row O-122, whose recorded residual risk is
the FTC's January 2015 AgeCheq decision. Do not read this passage as asserting 312.5(b)(2)(i): an
earlier draft cited a "sign and submit electronically" method there, and reading the provision
directly found no such method. **This paragraph makes no claim to the reader about which method
applies, and it must not acquire one**: a security or privacy claim in a public notice is an
enforceable representation under FTC Act §5 (register row O-38), so describing the flow as
"verified" or as satisfying a named method would convert an accepted internal risk into an
external misstatement. See counsel-engagement-brief.md Section 1.3, retained as record.]

Before that step, we ask an independent service, Kids Web Services (run by Epic Games), to
confirm that you are an adult. You choose your country, we send your email address to that
service, and it emails you a link to complete its own check. Your child's information is never
part of this: the service receives your email address, the country you chose, the language your
browser asked for, and a reference number that means nothing outside our system. It tells us only whether the check was confirmed
or refused, never how you completed it, and we never store a copy of your email address on the
adult-check record itself.

This step is about **who you are**, not about what you are agreeing to. Your permission is
still the name you type and the box you check, described above; the adult check is a separate
gate we put in front of it. [COUNSEL: this is exactly why the two are described separately, and
neither passage should be merged into a single "verified consent" claim. Please confirm the
split reads correctly for a lay guardian.]

[NOT YET LIVE for guardians as of 2026-08-10: this step runs on our internal staging tier only,
against the vendor's test environment, and is switched off in the live app. Do not publish this
passage until it is switched on, or a guardian will read a description of a step they never
encounter.]

### Who we share information with

We use the following outside companies (**processors**) to run the app. None of them may use
your or your child's information for their own purposes; each acts on our instructions only.
[COUNSEL: this processor-only claim is asserted for every vendor below, but
`processor-dpa-checklist.md` shows several DPAs not yet executed and open questions on specific
vendors (OpenRouter's account-wide Zero Data Retention setting and whether it covers every
downstream model provider it routes to; which Anthropic terms tier this account is on; whether
Google Perspective specifically is covered by the Cloud DPA). Please confirm whether this
statement can stand as written, needs to be qualified per vendor, or should be held until the
checklist closes before this notice is published. **Sharpened 2026-08-12**: for one vendor this is
no longer an open question but a probable contradiction. Kids Web Services' Parent Verification
terms (retained at `vendor-terms/epic-kws/`) list eight activities at cl. 2, and cl. 5 then makes
KWS our processor for only two of them and states that for the other six "you and KWS are each
independent
controllers". The **General** Terms' cl. 5.1 then says the record they build is theirs and "is used to provide KWS
Services to you and our other customers", which is the vendor using it for their own purposes.
Read straight, that is the opposite of the sentence above. Please rule on whether the Kids Web
Services row must be lifted out of this paragraph and described separately.]

| Company | What they receive | Why |
|---|---|---|
| Supabase | Your account and your child's profile data, stored in our database | Hosting and sign-in |
| OpenRouter and the AI model providers it routes to; Anthropic (direct) | Story prompts, screened to remove real names, contact details, and addresses before sending | Generating your child's stories |
| OpenAI Moderation, Google Perspective | Generated story text and story-idea text, similarly screened | Safety-checking story content before it reaches your child |
| Google (Gemini) | Cover-art prompts, similarly screened | Generating book cover art |
| Cloudflare (R2) | Cover art images, accessible only via a short-lived, non-public link | Image storage |
| Sentry | Error reports, designed to exclude your child's reading content | Fixing bugs |
| Epic Games (Kids Web Services) | **Your** email address, the country you selected, a language tag, and a reference number. Never your child's name, profile, or story content | Confirming that you are an adult before you can create a child profile |

**One thing to be clear about the adult check**: we send your email address to Kids Web
Services when the check *starts*, not when it succeeds. If you abandon it, if it comes back
refused, or if you never create an account at all after that point, your email address has
still been sent to them and is subject to their handling of it, not ours. There is no version
of this step that confirms an adult without disclosing the address first.

Kids Web Services also **keeps** a record of the check. Their terms describe it as a hashed
version of your email address together with how and when you were verified, the country your
device was in, and which apps you have verified for, held by them and reused across the other
services they provide. We do not receive that record and cannot see it.

[COUNSEL: three of the four asks previously here have moved.
(a) **Answered 2026-08-12**: the disclosure is now made *before* the guardian triggers the send,
in copy on the verification page itself, and its position ahead of the submit button is asserted
by test rather than left to convention. This notice is no longer the only place it appears.
(b) **Answered 2026-08-12, and neither prior guess was right**: the counterparty is Kids Web
Services Ltd, a company incorporated in **England** (Company Number 13351982), governed by the
laws of England and Wales. So this is a US-to-UK transfer, not US-to-US or US-to-EU, and the
"every company above is based in the United States" statement below is wrong rather than merely
uncovered. Please confirm the mechanism to name (UK IDTA, or the UK Addendum to the EU SCCs).
(c) **Narrowed 2026-08-12**: a Data Processing Addendum does bind us, incorporated by reference
at General Terms cl. 6, but it has not been retrieved or read, and per the note above a DPA
would not reach the six activities their terms treat as independent-controller processing.
(d) **New**: is the paragraph immediately above sufficient for what KWS retains and reuses, or
does Art. 13(1)(e) require naming them as an independent controller for that part in the table
itself? It is the one thing a guardian would not infer from "we send them your email address to
check you are an adult".]

We do not sell your or your child's information, and we do not use it for advertising — we
have no advertising or marketing SDKs of any kind in the parts of the app your child uses.

**International transfers**: every company above is based in the United States except Kids Web
Services, which is a **United Kingdom** company: Kids Web Services Ltd, incorporated in England,
with its registered office in London. Your email address goes to the UK when the adult check
runs. [COUNSEL: this replaces a hedge, corrected 2026-08-12 from the vendor's own terms
(`vendor-terms/epic-kws/`), which earlier drafts recorded as an unresolved choice between a US
and an EU Epic entity. It was neither. Two asks follow: confirm the transfer mechanism to
represent here for a US-to-UK transfer (the UK IDTA, or the UK Addendum to the EU SCCs; the
Data Privacy Framework does not apply in this direction), and confirm it is actually executed
before publication. As of this draft that paperwork (`coppa-gdpr-remediation-plan.md` Phase 5)
has not been completed for any vendor. Note the interaction with the decision to keep UK users
out of scope: that decision is about who uses the app, and does not follow through to a
processor that is itself a UK company.]

### How long we keep information

| Category | How long |
|---|---|
| Your active account and your child's active profile | For as long as the account/profile is in use |
| Reading progress, completions, ratings for a profile you've deactivated (not deleted) | Up to 90 days after deactivation, then deleted |
| A story request we blocked or you declined | The decision and category are kept; the original typed text is replaced with a placeholder 30 days after the decision |
| Raw story-generation output kept for troubleshooting | 30 days, or immediately once a story is published, whichever comes first |
| Records of admin safety reviews | 1-2 years |
| The adult-check record described above | Kept for as long as your account exists. [COUNSEL: this is a statement of current behaviour, not of a chosen policy: no deletion job covers this table, and `data-retention-policy.md` has no row for it. Please rule on a window, or confirm that keeping it alongside the consent record it supports is correct.] |
| Our internal record of who did what (an accountability log; never contains your child's name or story text, only ids and categories) | Kept indefinitely, as a legal-compliance and dispute-resolution record; see our published Article 17(3) analysis for why this category is treated differently from the rest |

### Your rights, and your child's

Because your child does not hold their own account, you exercise these rights on their
behalf as their guardian, as well as for your own information:

- **See what we have.** Request a full export of your family's data.
- **Correct it.** Update your child's profile settings, or your own account details, directly
  in the app.
- **Delete it.** Delete a single child's profile, or your entire family account, at any time;
  this is permanent.
- **Pause active use of a specific profile's data** without deleting it (for example, while
  you sort out a concern), separate from full deletion.
- **Complain.** If you are in the EU or UK, you have the right to complain to your local data
  protection authority. [COUNSEL: confirm whether we need to name a specific supervisory
  authority here, per the open UK/EEA-applicability question in our GDPR review.]

To exercise any of these, use the in-app controls in your guardian console, or email
byronawilliams@gmail.com.

### Security

We use industry-standard measures to protect your information, including encrypted
connections, strict access controls, and regular security reviews. See our published
security policy for more detail. No system is perfectly secure; if something goes wrong, we
follow a documented internal breach-response process.

### Changes to this notice

If we make a material change to this notice, we will ask you to review and re-confirm your
consent the next time you sign in. [Note: the re-consent-on-change flow itself is not yet
built — `coppa-gdpr-remediation-plan.md` Phase 2b — so this sentence describes intended, not
current, behavior. Do not publish this sentence until 2b ships, or adjust it to describe the
interim manual process.]

### Contact us

Questions about this notice or your family's information: byronawilliams@gmail.com.

---

## Notes for counsel (not part of the published notice)

1. Every `[COUNSEL: ...]` bracket above is a specific, flagged decision point; please resolve
   each before this notice is published, not just the document as a whole.
2. This notice deliberately mirrors the actual shipped mechanism (what data is collected, how
   consent is captured, what the retention windows are) rather than aspirational language, so
   that publishing it does not itself create a new compliance gap between what we say and what
   the code does. If any bracket above changes the design (e.g., a different transfer
   mechanism, a different retention window), the corresponding code/migration/remediation-plan
   entry should be updated to match, not just this document.
3. Once approved, publish this as an actual guardian-facing route (not just this markdown
   file) and link it from: the landing page, the guardian console, and
   `GuardianConsentPage.tsx`'s consent-capture screen (currently that screen references "our
   Privacy Notice" with no link — add one once this exists as a real page).
