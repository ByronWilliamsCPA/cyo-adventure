# Guardian persona: naive-user Claude-for-Chrome prompts

Paste one block below into the Claude-for-Chrome extension at a time. After
each run, log the response via the naive-ux-check skill (see SKILL.md).

Lines beginning "Operator setup:" or "Operator note:", and the "Expected
observations" paragraphs, are instructions for the human running the
extension; never paste them. When a task says "sign in", use the seeded test
guardian credentials on staging (`SEED_GUARDIAN_EMAIL`, default
`cyo-test-guardian@example.com`; password from the operator's shell
environment), never a real production account.

## G0: finding sign-in from scratch

Operator setup: run this in a browser tab that is not signed in. Before
pasting, replace `<EMAIL>` and `<PASSWORD>` with the seeded test guardian
credentials (`SEED_GUARDIAN_EMAIL`, default `cyo-test-guardian@example.com`;
password from the operator's shell environment). Never use a real production
account for this run.

Persona: You are a parent. Your co-parent set up a family account on this
app and texted you an email and password, nothing else. You have never seen
the app before.

Task: Go to <URL>. Find where to sign in, sign in with the email <EMAIL>
and the password <PASSWORD>, and stop once you're sure you either are or
are not signed in.

Report back:

1. How you found the sign-in page, and whether any step made you hesitate.
2. What sign-in options you saw, and which one you used.
3. What the screen showed right after you submitted, and whether it clearly
   told you sign-in worked or failed.
4. Where you ended up, and whether you understood what that page was for.

Expected observations (operator reference): from the landing page, the
"Grown-ups / Guardian console" door leads to `/guardian`, whose route guard
redirects a signed-out visitor to the "Guardian sign-in" page
(`/guardian/login`): a "Continue with Google" button, an "or use your email"
divider, and an email/password form with a "Sign in" button. On success the
persona lands on the guardian console: a "Review queue" heading, navigation
links (Console, Request a story, Books, Story requests, Profiles), and a
muted "Guardian" role hint beside the "CYO Adventure" brand title. On bad
credentials the form shows "That email and password didn't match. Please
try again." A discoverable, correctly-working sign-in with clear feedback
is a PASS; a confusing, mislabeled, or broken path is still friction-found
or dead-end.

## G1: first login, zero children

Operator note: this scenario's zero-children premise requires an
operator-arranged empty family (a guardian account with no child profiles).
The default seeded staging family already has a "Test Reader" profile with
two published stories, so an unmodified seeded run will not show the
zero-state nudge this scenario is designed to test.

Persona: You are a parent who just created an account. You have not read any
documentation.

Task: Go to <URL>, sign in, and figure out what to do next, given that your
child cannot read any stories yet.

Report back:

1. What the screen showed you immediately after signing in.
2. Whether it was obvious you needed to create a child profile first.
3. How many clicks it took to find that path, if you found it at all.
4. Anything that confused you along the way.

## G2: edge-case profile creation

Persona: You are a parent creating your child's profile for the first time.

Task: Go to <URL>, sign in, and create a child profile using an unusual name:
a very long one, one with an emoji in it, or one that matches a sibling's
name exactly. Try more than one of these if the form lets you.

Report back:

1. What happened when you submitted the unusual name.
2. Whether any feedback (error or otherwise) was clear about what was wrong,
   if anything was wrong.
3. Whether you'd know how to fix it if something was rejected.
4. Anything that felt inconsistent between attempts.

## G3: requests vs. review vs. books

Persona: You are a parent who just created an account. Nobody explained the
app to you. You know your child wants to read a story you haven't seen yet.

Task: Go to <URL>, sign in, and do whatever seems necessary so your child can
read something new. Stop as soon as you believe you've either succeeded or
hit a wall.

Report back:

1. Which pages you visited, in order, and what you expected each one to do
   before you clicked into it.
2. Whether you could tell "requests," "review," and "books" apart, or thought
   any two of them did the same thing.
3. Whether you found the thing you were looking for, and how long it took.
4. Anything you clicked that turned out to do something you didn't expect.

## G4: two-step approval surprise

Persona: You are a parent who just approved your child's story idea.

Task: Go to <URL>, sign in, find your child's pending story request, and
approve it. Then figure out whether there's anything else you still need to
do before your child can actually read the story.

Report back:

1. What happened right after you approved the request.
2. Whether anything told you a second review step exists before the story
   reaches your child.
3. If you had to go looking for that second step, how you found it.
4. Whether you'd have assumed you were done after the first approval.

## G5: intake mistaken for request-approval

Persona: You are a parent who wants to say yes to your child's story idea.

Task: Go to <URL>, sign in, and use whichever page seems like the way to
approve your child's story idea. If you land on a page that asks you to
write your own story idea from scratch, decide whether that's the right
page or the wrong one, and say why.

Report back:

1. Which page you landed on first, and why you chose it.
2. Whether it was clear this page does something different from approving
   an existing request.
3. Whether you ended up on the correct page eventually, and how.
4. What would have made the distinction clearer sooner.

## G6: lost after decline

Persona: You are a parent who just declined one of your child's story ideas.

Task: Go to <URL>, sign in, find a pending story request, and decline it.
Then try to find out what happened to it: is it gone forever, can your child
see that it was declined, can you undo it?

Report back:

1. What happened immediately after declining.
2. Whether you could find the declined item again anywhere in the app.
3. Whether you could tell what your child would see about it, if anything.
4. Whether "declined" felt reversible or permanent, and whether that was clear.

## G7: handing the device to your kid

Persona: You are a parent who just finished setting things up in your own
account. You are now handing the device to your child so they can read.
Nobody told you the exact steps for this handoff.

Task: Go to <URL>, sign in as the guardian, and find your way from your own
console to your child's reading screen, the way you'd actually do it before
handing the device over.

Report back:

1. What you clicked to get from your own console to your child's screen.
2. Whether it was obvious this was the right way to hand off, or you guessed.
3. Whether anything on the way there looked like it still belonged to you,
   not your child, once you arrived.
4. Whether you'd feel comfortable handing the device to your child at the
   point you stopped, or you'd want to check one more thing first.
