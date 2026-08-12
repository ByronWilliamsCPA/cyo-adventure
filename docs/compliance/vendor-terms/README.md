---
title: "Retained Vendor Terms"
schema_type: common
status: published
owner: core-maintainer
purpose: "Durable, versioned store of the vendor contract documents this project's compliance records cite by clause number, so a citation stays checkable after the vendor changes its terms."
tags:
  - compliance
  - privacy
  - legal
---

Created 2026-08-12, when the Kids Web Services terms became the first vendor documents cited by
clause number in `docs/security/assurance-register.md` and `processor-dpa-checklist.md`.

## Why this exists

Compliance records here cite vendor terms by clause number: "PV Terms clause 5", "General Terms
clause 6". A clause number is only meaningful against a specific version of a specific document,
and vendor terms change under you. Kids Web Services' Parent Verification terms reserve the right
to change verification methods "upon reasonable notice (up to 14 days)", with continued use
counting as agreement (clause 4). An acceptance recorded against methods that no longer exist is
worse than no record, because it reads as current.

So the rule is: **if a compliance record cites a vendor document by clause, the bytes of that
document live here.** A link to the vendor's live page is not a substitute. The live page is
whatever the vendor is serving today; the citation was written against what they served on a
particular day, and only one of those two is a fact about our decision.

## Layout

```text
docs/compliance/vendor-terms/
├── README.md                        <- this file: the convention plus the index
└── <vendor-slug>/
    └── <document-slug>-<version-date>.pdf
```

`<version-date>` is **the vendor's own "Last updated" date**, ISO-formatted, not the date we
downloaded it. Two consequences, both deliberate:

- A clause citation elsewhere in the repo can name the exact file, and the filename alone says
  which version it is.
- Supersession is visible from `ls`. Two files with the same document slug and different dates
  means the terms changed, and the older one is what some earlier decision was made against.

**Never overwrite or delete a superseded document.** When a vendor issues a new version, add it
alongside. The question a superseded file answers, "what did we actually agree to when we made
that call", has no other source once the file is gone.

## Adding a document

1. Save the PDF as the vendor serves it. Do not re-print, re-export, or flatten it: the retained
   artifact should hash to the same bytes the vendor published, or the hash below proves nothing
   about the vendor's document.
2. Name it `<document-slug>-<version-date>.pdf` using the vendor's own "Last updated" date.
3. `sha256sum` it and add a row to the index below.
4. Add or extend the `REUSE.toml` annotation (see "Licensing" below). The blanket `docs/**` rule
   marks everything CC-BY-4.0 and copyright Byron Williams, which for a vendor's contract would be
   an affirmatively false ownership claim. Every file in this directory needs its own annotation
   naming the actual rights holder.
5. Record which compliance rows cite it, in the index's last column. That column is what makes a
   terms change actionable: when a new version arrives, it names the rows to re-check.

## Licensing

These are third-party documents, retained as a record of terms presented to us. They are not our
work, not licensed to us for redistribution, and are annotated in `REUSE.toml` as
`LicenseRef-Vendor-Terms` with the vendor as copyright holder. See
`LICENSES/LicenseRef-Vendor-Terms.txt`.

## Index

| Vendor | Contracting entity | Document | Vendor version date | Retrieved | SHA-256 | Cited by |
|---|---|---|---|---|---|---|
| Epic Games (Kids Web Services) | Kids Web Services Ltd, a private limited company incorporated in England, Company Number 13351982, registered office C/O Shepherd And Wedderburn LLP, 1-6 Lombard Street, London EC3V 9AA, United Kingdom | [KWS General Terms](epic-kws/kws-general-terms-2026-05-13.pdf) (12pp) | 2026-05-13 | 2026-08-12, supplied by the account owner from the KWS Control Panel | `0786d6e425c765baa1320adfc1bc88177fcceb154fe10b4e706d209ddd221cdc` | `assurance-register.md` O-125; `processor-dpa-checklist.md` Epic row; `privacy-notice.md` transfers paragraph |
| Epic Games (Kids Web Services) | as above | [KWS Service Specific Terms: Parent Verification](epic-kws/kws-parent-verification-service-terms-2025-08-28.pdf) (3pp) | 2025-08-28 | 2026-08-12, supplied by the account owner from the KWS Control Panel | `8194f057f5a306ed83c22cb271d4792ca5836431af3909712f1699abfd3e7270` | `assurance-register.md` O-122, O-124, O-125; `processor-dpa-checklist.md` Epic row; `privacy-notice.md` processor claim and transfers paragraph |

Verify every retained document still matches its row. Run from this directory; it reads the
hash and the path out of the table above, so it needs no separate checksum file to drift from
the index:

```bash
awk -F'|' '/^\| Epic/ { p=$4; sub(/^[^(]*\(/, "", p); sub(/\).*$/, "", p);
    gsub(/[ `]/, "", $7); print $7 "  " p }' README.md | sha256sum -c
```

Expect one `: OK` per row and exit 0. A `FAILED` line means the bytes on disk are not the ones
the citations elsewhere in the repo were written against, which is a finding, not a filing
error: re-open every row named in that document's "Cited by" column.

Uses only `sub()` rather than gawk's three-argument `match()`, so it behaves the same under
mawk, which is the default `awk` on Debian and Ubuntu.

## What is not stored here

- **Vendor pages that are not contract documents** (pricing, status, marketing). Link to those.
- **Documents incorporated by reference that we have not retrieved.** The KWS General Terms
  incorporate a Data Processing Addendum by reference at clause 6; that DPA is not in this
  directory because it has not been retrieved yet. That absence is itself tracked, at
  `assurance-register.md` O-125. An incorporated document is as binding as the one that
  incorporates it, so a gap here is a gap in the record, not a filing detail.
- **Anything containing credentials.** Vendor terms are public documents. Order forms, invoices,
  and Control Panel exports may not be; do not add them without checking.

## Relationship to other compliance documents

| Document | Relationship |
|---|---|
| `processor-dpa-checklist.md` | The to-do list of DPAs to execute. Rows there cite documents here. |
| `docs/security/assurance-register.md` | Where an accepted risk records what it relies on. When a retained document changes, the "Cited by" column names the rows to re-open. |
| `privacy-notice.md` | The guardian-facing statement. Its processor and transfer claims must be true against the documents here, not against what we assume a vendor's posture to be. |
| `records-of-processing-activities.md` | Article 30 record; its recipient and transfer-mechanism entries are downstream of what these documents actually say. |
