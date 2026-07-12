# Admin persona: naive-user Claude-for-Chrome prompts

Admins reuse every /guardian/* page under role=admin; there is no dedicated
admin route tree. The visible differences from a guardian session: the
console shell shows a muted "Admin" role hint beside the "CYO Adventure"
brand title and hides the guardian-only "Books" nav link (PR #206), and the
Console page itself renders admin-only content: the embedded story-request
form runs in admin mode with a cross-family "Choose a family…" picker
(guardians only ever pick among their own children), and a "Moderation
admin" nav block links to the moderation dashboard and thresholds. These
prompts probe whether that reuse is legible to someone who was just handed
admin access with no onboarding.

Lines beginning "Operator setup:" or "Operator note:", and the "Expected
observations" paragraphs, are instructions for the human running the
extension; never paste them. When a task says "sign in", use the seeded test
admin credentials on staging (`SEED_ADMIN_EMAIL`, default
`cyo-test-admin@example.com`; password from the operator's shell
environment), never a real production account.

## A0: admin sign-in, no onboarding

Operator setup: run this in a browser tab that is not signed in. Before
pasting, replace `<EMAIL>` and `<PASSWORD>` with the seeded test admin
credentials (`SEED_ADMIN_EMAIL`, default `cyo-test-admin@example.com`;
password from the operator's shell environment).

Persona: You were just told you're an admin on this app, with no other
explanation of what that means. You've been given an email and a password
and nothing else.

Task: Go to <URL>. Find where an admin is supposed to sign in, sign in with
the email <EMAIL> and the password <PASSWORD>, and stop once you're signed
in.

Report back:

1. How you decided where to sign in, and whether anything along the way said
   "admin" or hinted that admins belong there.
2. Whether the sign-in page itself gave any admin-distinct signal, or looked
   purely parent-facing.
3. What the first screen after sign-in showed, and whether anything on it
   told you that you are an admin.
4. How confident you are that you signed in "as an admin" rather than as a
   regular parent, on a scale of "certain" to "no idea."

Expected observations (operator reference): the landing page's "Grown-ups /
Guardian console" door carries the note "Admins sign in here too" (the only
pre-sign-in admin signal); the sign-in page is titled "Guardian sign-in"
with no admin mention; after sign-in, the console header shows a muted
"Admin" role hint beside the "CYO Adventure" brand title (PR #206), the
"Books" nav link is absent (it is guardian-only), and the Console page
shows admin-only content: a story-request form with a cross-family
"Choose a family…" picker and a "Moderation admin" nav block (moderation
dashboard and thresholds links). A persona reporting the family picker or
moderation links has found decisive admin evidence, stronger than the
header hint; credit it accordingly. A discoverable, correctly-working
sign-in is a PASS even if the persona only noticed the subtler signals;
note in the log which signals it found. A confusing, mislabeled, or broken
sign-in path is still friction-found or dead-end.

## A1: indistinguishable surface

Persona: You were just told you're an admin on this app, with no other
explanation of what that means.

Task: Go to <URL>, sign in, and try to figure out what, if anything, you can
do that a regular parent account couldn't.

Report back:

1. What, if anything, looked different from what you'd expect a parent
   account to see.
2. Whether you found any action that felt admin-specific.
3. How confident you are that you have elevated capability at all, on a
   scale of "certain" to "no idea."
4. What you would look for next if you still weren't sure.

## A2: minimum-viable intake

Persona: You are an admin trying to generate a new story as quickly as
possible.

Task: Go to <URL>, sign in, and submit a new story request filling in only
whatever fields are required, skipping every optional one.

Report back:

1. Which fields you filled and which you skipped.
2. Whether the flow still made sense with the minimum filled in.
3. What happened after submitting.
4. Anything that felt like it needed more input than you gave it, even
   though it let you proceed.

## A3: rubber-stamp approval friction

Persona: You are an admin who just generated a story and wants to approve it
immediately without reading it closely.

Task: Go to <URL>, sign in, find a story awaiting your review, and try to
approve it as fast as possible without opening or reading any flagged
passage.

Report back:

1. Whether the interface let you approve without looking at anything flagged.
2. Whether anything slowed you down or asked you to confirm you'd reviewed it.
3. How many clicks the fastest path to approval took.
4. Whether that speed felt appropriate for a safety checkpoint, or too easy.
