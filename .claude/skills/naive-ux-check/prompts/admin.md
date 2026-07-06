# Admin persona: naive-user Claude-for-Chrome prompts

Admins reuse every /guardian/* page under role=admin; there is no dedicated
admin UI. These prompts probe whether that reuse is legible to someone who
was just handed admin access with no onboarding.

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
