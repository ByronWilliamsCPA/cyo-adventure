---
title: "Control Inheritance Map"
schema_type: common
status: published
owner: core-maintainer
purpose: "Register of every security control CYO Adventure does not implement itself: which
  out-of-repo control plane provides it, whether it applies to production today, the evidence,
  and the event that requires re-validation."
tags:
  - security
  - reference
  - compliance
---

Audited: 2026-08-02.
Companion to: [`crypto-inventory.md`](crypto-inventory.md), which uses this same owner-column
format scoped to cryptography only. This file generalises it to all inherited controls.
Update trigger: any change to a control plane listed below, and any conversion between
deployment tiers (R1 internal-web, R2 TestFlight, R3 App Store).

## Why this file exists

A repository-scoped review can only see three of the five places a control can live:

| Layer | Example | Covered by existing gates |
|-------|---------|---------------------------|
| L1 source | middleware, validators | yes (Ruff, BasedPyright, Bandit, tests) |
| L2 dependency graph | CVEs in pinned deps | yes (pip-audit, OSV, Dependabot) |
| L3 built container | image CVEs, build args | yes (Trivy, container-security.yml) |
| **L4 deployed runtime config** | Traefik middleware, firewall rules, DNS proxy status | **no** |
| **L5 operational capability** | Cloudflare WAF, Supabase RLS state, R2 bucket policy | **no** |

Every control at L4 and L5 lives in an out-of-repo **control plane**. Nothing in CI reads those
planes, so their posture is asserted in prose and never measured. That is how a control ends up
documented as working while being structurally unable to function.

This file does not enforce anything and does not block a release. Its contract is narrower and
is the one that was missing: **an inherited control must have a named owner, a stated
applies-today verdict, and a named re-validation trigger.** An entry may legitimately read
"does not apply, by design, for this release tier." What it may not do is go unrecorded.

## Verification vantage rule

Adopted 2026-08-02 after a false negative produced while building this file.

> **A control that describes posture at a trust boundary must be verified from outside that
> boundary. A check that runs inside the boundary it is testing is a hollow check by
> construction.**

Worked example. Public DNS for `cyo.williamshome.family` was measured from a workstation on the
home LAN and returned `192.168.1.209` from `1.1.1.1`, `8.8.8.8`, and `9.9.9.9`, which reads as
"the record is not proxied." The result was fabricated: split-horizon DNS transparently
intercepts all outbound port-53 traffic and answers it locally, regardless of the destination
address the query is sent to. The tell is that queries addressed to the zone's own authoritative
Cloudflare nameservers (`kobe.ns.cloudflare.com`, `sky.ns.cloudflare.com`) returned the same
RFC1918 answer, which those servers cannot produce. The true state is the opposite of the
measurement: `cyo`, `cyo-dev`, and `cyo-staging` are all A records to `66.42.78.207` with the
proxy enabled.

Consequence for tooling: external-posture checks belong on a GitHub-hosted runner or a probe
running on the VPS, never on a developer machine. This is the acceptance criterion for any
future dynamic assurance job.

## Plane A: Cloudflare (zone `williamshome.family`)

Proxy status verified from the Cloudflare dashboard on 2026-08-02: `cyo`, `cyo-dev`, and
`cyo-staging` are each an A record to `66.42.78.207`, all Proxied. Zone-level settings below were
read from the same session.

| # | Control | Applies today | Evidence | Re-validate when |
|---|---------|---------------|----------|------------------|
| A1 | Edge TLS termination | Yes, for traffic that arrives via the edge | Proxy enabled | Proxy status change |
| A2 | WAF / managed rules | **Advisory only** (see A9) | Proxy enabled | Proxy status change; A9 closure |
| A3 | DDoS and rate limiting | **Advisory only** (see A9) | Proxy enabled | Proxy status change; A9 closure |
| A4 | Bot mitigation | **Advisory only** (see A9) | Proxy enabled | Proxy status change; A9 closure |
| A5 | HTTP to HTTPS redirect at edge | **No rule configured** | Rules gallery shows only "Create from template" for every entry | Any Rules change |
| A6 | Origin certificate validation | Yes, but **not pinned** | Mode is "Automatic SSL/TLS"; badge reads "Currently running: Full (strict)"; next scan Aug 7 | Every Cloudflare re-scan |
| A7 | Post-quantum key exchange to origin | Automatic key exchange ON; compliance checkboxes observed **unsaved** | Dashboard, 2026-08-02 | Origin TLS stack change; ADR-013 review |
| A8 | Network Error Logging | **Yes, enabled** | Zone Network settings | Privacy model review |
| A9 | **Origin reachable directly, bypassing the edge** | **Yes: confirmed defect** | See below | On closure |
| A10 | Web Analytics / RUM | Not enabled | "No data available" | If observability plan adopts it |
| A11 | IP Geolocation (`CF-IPCountry`) | Enabled, unused by the app | Zone Network settings | If the app starts consuming it |
| A12 | Maximum upload size | 100 MB at edge vs `client_max_body_size 2m` at nginx | Zone Network settings; `frontend/nginx.conf:132` | Upload feature change |

Also observed and recorded so they are not re-raised: IPv6 compatibility ON, WebSockets ON,
gRPC OFF, Pseudo IPv4 Off, Onion Routing OFF, True-Client-IP unavailable (Enterprise-only).
The three SendGrid CNAME records in this zone were triaged previously and are accepted as-is.

### A9: origin bypass (open defect)

The origin serves the full application on `:443` with Cloudflare entirely out of the path:

```console
$ curl --resolve cyo.williamshome.family:443:66.42.78.207 https://cyo.williamshome.family/
HTTP/2 200
server: nginx
strict-transport-security: max-age=31536000; includeSubDomains; preload
(no cf-ray)
```

Two `homelab-infra` facts compose with this:

- `services/pangolin/vps/scripts/03-firewall-setup.sh:61` opens `443/tcp` with no source
  restriction.
- `middleware.yml:321-332` shows the `pangolin-source-verify` IP allowlist was deleted.

The origin address is not secret: it is the A-record value, it is in DNS history, and it is
committed to `homelab-infra/dns-backups/`. Consequence: A2, A3, and A4 protect only clients that
arrive via the edge voluntarily. They are advisory, not enforcing, until the origin refuses
requests that did not come through the edge.

Remediation owner: `homelab-infra`, not this repository.

#### Why the firewall is the wrong enforcement point

`services/pangolin/vps/scripts/03-firewall-setup.sh` is otherwise deliberately hardened: port 80
is closed (DNS-01 ACME, so there is no HTTP-01 dependency), SSH is reachable only through the
management tunnel, and all three WireGuard ports are pinned to the OPNsense WAN IP. Line 61 is
the only unrestricted rule in the file.

It cannot simply be narrowed, because a `ufw` rule matches on address and port and cannot see the
requested hostname. Five records point at `66.42.78.207`; four are Proxied and
`auth.williamshome.family` is **not** (evidence: `dns-backups/williamshome.family-20260712T211442Z.json`,
dated 2026-07-12, so confirm before acting). Restricting `443/tcp` to Cloudflare ranges would
take `auth` offline, and no firewall exception can distinguish the two hostnames on a shared
socket.

Enforcement therefore belongs at Traefik, which is hostname-aware, per-router.

#### Ordering constraint: recovering the real client IP comes first

`traefik_config.yml` has no `forwardedHeaders.trustedIPs` block, so Traefik treats the socket peer
as the client address. That is correct today precisely because clients connect directly. Once
traffic is forced through Cloudflare, every request appears to originate from a Cloudflare edge
IP, which breaks two live controls:

- `13-configure-geo-restriction.sh:280` bans on `evt.Meta.source_ip`, so it would evaluate the
  edge's country rather than the visitor's.
- A CrowdSec or fail2ban decision would ban a Cloudflare edge IP, cutting off every legitimate
  user routed through that edge.

This shares a root cause with the `consent_ip` defect: nothing in the chain recovers the true
client address once a proxy is inserted.

#### Agreed remediation sequence

1. Add `forwardedHeaders.trustedIPs` (Cloudflare ranges) to the websecure entrypoint in
   `traefik_config.yml`. **Must land first**, or steps 2 and 3 cause an outage.
2. Enforce edge-only at Traefik, attached only to the CYO routers
   (`services/cyo-adventure/docker-compose.yml:392-398`). Interim form: restore a
   `pangolin-source-verify`-style `IPAllowList`. **Target form: Cloudflare Authenticated Origin
   Pulls (mTLS)**, adopted 2026-08-02 because mTLS is already established practice in this
   environment; it is hostname-precise, does not go stale when Cloudflare adds ranges, and is not
   defeated by learning the origin IP.

   The existing pattern transplants directly. `homelab-infra`
   `services/traefik/dynamic/tls.yml:69-75` defines an `internal-mtls` TLSOption
   (`clientAuthType: RequireAndVerifyClientCert` over `caFiles: /certs/internal-ca.crt`), applied
   per-router rather than globally, which is exactly the granularity needed here. The VPS Traefik
   already runs a `file:` provider (`services/pangolin/vps/config/traefik/traefik_config.yml:54-55`),
   so a new TLSOption drops in without restructuring.

   Two qualifications:

   - **Different instance, different CA.** `internal-mtls` lives on the homelab Traefik, on the
     `websecure-internal` entrypoint, authenticating device certificates issued by step-ca.
     Origin pulls must be enforced on the **VPS** Traefik against **Cloudflare's** origin-pull CA.
     Do not merge the two CA pools into one TLSOption: a shared pool would let any homelab device
     certificate satisfy the CYO router, and any Cloudflare-issued origin-pull certificate satisfy
     internal mTLS. Define a separate, dedicated TLSOption.
   - **Use per-hostname origin pull certificates, not zone-level.** Zone-level Authenticated
     Origin Pulls validate against a certificate Cloudflare shares across all customers, so it
     proves only "arrived via Cloudflare," not "arrived via this zone." A customer-supplied
     per-hostname certificate is what makes the control actually bind to this account.

   Issuing CA decision, 2026-08-02: **step-ca**. The origin-pull certificate is a client
   certificate in a private trust relationship between Cloudflare and the origin, never validated
   by a browser, so public trust adds nothing. `clientAuthType: RequireAndVerifyClientCert`
   verifies only that the chain reaches an anchor in `caFiles`, and Traefik has no built-in
   subject or SAN filter for client certificates, so the strength of the control equals the
   issuance surface of the trusted CA.

   - ZeroSSL is rejected: trusting a public CA root means every certificate that CA has ever
     issued authenticates to the origin.
   - Cloudflare's own CA is the rejected zone-level option above.
   - step-ca must be issued under a **separate root or dedicated intermediate**, not the one at
     `services/traefik/dynamic/tls.yml:74`. Sharing an anchor would let every homelab device
     certificate satisfy the CYO edge router.
   - Lifetime: issue long-lived and diarise rotation. Existing renewal tooling
     (`services/cert-enroll/scripts/renew-cert.sh`) pushes certificates to devices; Cloudflare
     requires an API upload instead, so short step-ca defaults would cause a recurring outage.
     Automating the Cloudflare-side upload is a follow-up, not a prerequisite.

   Evaluated and rejected for A9, 2026-08-02: **Cloudflare Client Certificates**
   (`developers.cloudflare.com/ssl/client-certificates/`). That product secures the
   client-to-edge leg, where a connecting client presents a certificate and Cloudflare verifies
   it at the edge via mTLS rules (`cf.tls_client_auth.cert_verified`). A9 is a bypass of the edge
   entirely, so a control enforced at the edge cannot see the traffic it would need to reject.
   Adopting it would make A9 more urgent rather than less, because edge-enforced access control
   fails open for anyone reaching the origin directly.

   Its certificates should also not be repurposed as the origin-pull certificate. Cloudflare
   validates them "against CAs set at the account level," which describes where the validation
   list is configured, not that the issuing root is cryptographically unique per account. If
   account scoping is enforced in Cloudflare's validation logic rather than in the chain, then
   trusting that root at the origin would accept client certificates issued to any Cloudflare
   customer, which is the same union problem as ZeroSSL. Unverified either way, and step-ca has
   no such ambiguity.
3. Widen or replace `--forwarded-allow-ips=172.16.0.0/12` (`Dockerfile:148`) so the backend
   recovers the guardian's address. Safe only after step 2, otherwise the header is
   attacker-supplied.

Contingent, not scheduled: proxying `auth.williamshome.family` would additionally unlock a
kernel-level `ufw` backstop beneath all of the above. **Open investigation (owner: maintainer,
2026-08-02): whether proxying `auth` breaks anything.** Viable only if `auth` is plain HTTPS.

Explicitly rejected: narrowing `ufw` alone. On current DNS it takes `auth` offline, and without
step 1 it silently corrupts geo-restriction and ban logic.

## Plane B: Supabase dashboard (project `cvrnaydpzijtszfbsraq`)

| # | Control | Applies today | Evidence | Re-validate when |
|---|---------|---------------|----------|------------------|
| B1 | RLS enabled on all tables | Yes, all 25 | Live read-only probe, 2026-08-02 | Every new-table migration |
| B2 | No `anon` / `authenticated` policies | Yes | Probe: reads return `200 []`, writes `42501` | Every policy migration |
| B3 | `anon` role table grants | **Full DML grants present** | `supabase/migrations/20260729000000_add_child_profile_personalization.sql:48-56` | Continuous |
| B4 | OIDC / JWKS configuration | Assumed correct, unverified | none | Auth provider change |

B3 is the live risk and it is a single-layer defence, not an exposure. The `USING(true)` policies
are scoped `TO cyo_api, cyo_worker` and never to `anon`, so no data is reachable today. But
because `anon` holds the underlying grants, RLS is the only thing standing between the public
PostgREST endpoint and the tables. Adding `ALTER DEFAULT PRIVILEGES` plus explicit revokes would
make it two-layer.

Correction owed: ADR-022 context point 3 asserts that `anon` and `authenticated` "have no
grants." That is false, and the migration cited in B3 is the authoritative contradiction.

## Plane C: homelab-infra (Pangolin / Newt / Traefik / nginx)

This is where the controls that are actually enforcing live.

| # | Control | Applies today | Evidence | Re-validate when |
|---|---------|---------------|----------|------------------|
| C1 | Public TLS termination | Yes | Pangolin VPS | Infra change |
| C2 | Response security headers | Yes, and **overwrites** the app's stronger CSP | `middleware.yml:112-129` uses `Header().Set()` | Any header change in either repo |
| C3 | HSTS | Yes, unconditional | `middleware.yml` | Infra change |
| C4 | Source IP allowlist | **Deleted** | `middleware.yml:321-332` | See A9 |
| C5 | Host firewall | `443/tcp` open to the world | `03-firewall-setup.sh:61` | See A9 |

C2 is the reason an in-repo CSP fix does not work. Traefik `Set()`s the header, so a
`frontend/nginx.conf` CSP is discarded before any client sees it. The four-directive CSP observed
in production responses is Traefik's, not the ten-directive one in
`src/cyo_adventure/middleware/security.py:113-124`. Any CSP change must land in `middleware.yml`.

Correction owed: `docs/architecture/deployment.md:46-48` describes this chain incorrectly, and
`crypto-inventory.md:68` names `cloudflared` for the edge-to-origin tunnel. The tunnel is
Newt/WireGuard behind Pangolin; `cloudflared` is not deployed.

## Plane D: GitHub repository settings

Branch protection, required status checks, merge-queue configuration, and ruleset membership are
configured through the GitHub API and are not represented in any tracked file. This plane has
already produced at least one silent gate failure in this project's history, where a required
check could not fail.

| # | Control | Applies today | Re-validate when |
|---|---------|---------------|------------------|
| D1 | Required status checks | Assumed, unverified | Any workflow rename or deletion |
| D2 | Branch protection on `main` | Assumed, unverified | Ruleset change |
| D3 | Merge queue configuration | Assumed, unverified | Ruleset change |

A workflow rename silently detaches a required check without any signal, which makes D1 the
highest-value candidate for an automated read of the settings API.

## Plane E: Cloudflare R2 (cover-art object storage)

| # | Control | Applies today | Re-validate when |
|---|---------|---------------|------------------|
| E1 | Bucket public/private posture | Unverified | Any covers change |
| E2 | CORS policy | Unverified | Frontend origin change |
| E3 | Object lifecycle / retention | Unverified | Retention policy decision |

Not represented in any repository artifact. Covers are child-associated content, so E1 in
particular needs a recorded verdict.

## Open items produced by this audit

Each needs a `UW-*` row so it has a phase home. None of them blocks a release.

1. **A9 origin bypass** (`homelab-infra`). Highest severity, smallest change.
2. **`consent_ip` is correct today and will silently break on the first external consent.**
   `db/models.py:502` stores `consent_ip` as the evidentiary record of parental consent and
   carries an `#ASSUME` that it holds the real client address; `api/deps.py:857-862` repeats it.
   The chain is `frontend/nginx.conf:114` (`$proxy_add_x_forwarded_for`) into uvicorn 0.51.0,
   whose `ProxyHeadersMiddleware` walks `X-Forwarded-For` right-to-left and stops at the
   rightmost address outside `--forwarded-allow-ips`, which `Dockerfile:148` sets to
   `172.16.0.0/12` only.

   Measured against production on 2026-08-02 with a counts-only query returning no addresses.
   The `"user"` table holds 6 rows, 2 with a consent record, across 2 families and 2 distinct
   signer names, resolving to **1 distinct address in `192.168.0.0/16`**, with zero in
   `172.16.0.0/12` and zero loopback. `personalization_disclosure_consent` is empty.

   Reading: the mechanism **works** on the internal path. A `192.168` value is a real LAN client,
   not a container address, which means the Docker hops are correctly treated as trusted and the
   true client is recovered. Two signers sharing one address is consistent with both accounts
   having been created from the same machine and is not evidence of a defect.

   What it actually shows is that **every consent on record was captured from the LAN**, so no
   consent has yet traversed Cloudflare and the data cannot speak to the external path at all.
   The forward risk stands: once a guardian consents from outside the LAN, the rightmost address
   outside `172.16.0.0/12` becomes the Cloudflare edge rather than the guardian, and the record
   degrades with no error and no log line. There is no corrupted evidence to remediate today, and
   this must be fixed before any guardian can consent from off-LAN.

   Ordering constraint: switching to `CF-Connecting-IP` is only safe **after** A9 is closed,
   otherwise the header becomes attacker-controlled.
3. **A6**: pin `Full (strict)` explicitly rather than leaving SSL/TLS on Automatic.
4. **A8**: accept-or-disable decision on Network Error Logging, which sends child-device
   connectivity reports (URL, timestamp, client IP) to Cloudflare and is absent from the privacy
   model.
5. **B3**: revoke `anon` grants to make RLS two-layer; correct ADR-022 context point 3.
6. **A7 / ADR-013**: the edge-to-origin leg exists and the PQ setting is live, but ADR-013 names
   a component that is not deployed. Re-point it at Newt/WireGuard and Pangolin.
7. **Plane D and E** have no verified rows at all.

## Relationship to existing registers

This file records **posture**. It deliberately does not duplicate:

- `crypto-inventory.md`, which is the same instrument scoped to cryptography. One gap worth
  noting: its row 2 (client to Cloudflare edge, "already hybrid") can be skipped entirely while
  A9 is open, dropping a client straight onto row 3's classical leg.
- `docs/planning/unscheduled-work-register.md`, which records **scheduling**. Every open item
  above belongs there as well; this file is not a substitute for a phase home.
