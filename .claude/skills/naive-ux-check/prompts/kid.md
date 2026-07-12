# Kid persona: naive-user Claude-for-Chrome prompts

Paste one block below into the Claude-for-Chrome extension at a time. After
each run, log the response via the naive-ux-check skill (see SKILL.md).

Lines beginning "Operator setup:" or "Operator note:", and the "Expected
observations" paragraphs, are instructions for the human running the
extension; never paste them. Paste only the Persona / Task / Report back
block.

## K0: fresh device, no guardian ever signed in

Operator setup: run this in a fresh browser profile (or a new incognito
window) where no guardian has ever signed in to this app. Do not sign in
first; this is the one kid scenario that must start with no session at all.

Persona: You are a 7-year-old who was just handed a brand-new tablet. Nobody
in your family has used this app on it before, and no grown-up is nearby
right now.

Task: Go to <URL> and try to start reading a story, using only what's on
the screen.

Report back:

1. What you clicked, in order, and why at each step.
2. What the screen told you when you couldn't go any further, in your own
   words.
3. Whether that screen felt friendly and clear about what to do next, or
   like something was broken.
4. Whether you knew what to do next (even if it was "go find a grown-up"),
   or felt stuck.

Expected observations (operator reference): the kid picker at `/kids` should
show the differentiated auth gate shipped in PR #198 (source of truth:
`frontend/src/kid/ProfilePickerPage.tsx`): the title "Ask a grown-up to
help", the description "A grown-up needs to sign in before you can pick
who's reading.", a mascot illustration, and a single "I am a grown-up"
action link to the guardian sign-in page. No "Try again" control and no
"Oops, we hit a snag" error should appear. A friendly, correctly-working
gate like this is a PASS for this scenario; a confusing, mislabeled, or
broken gate is still friction-found or dead-end.

## K1: cold start, zero profiles

Operator setup: Before pasting this prompt, sign in as the seeded test
guardian (`SEED_GUARDIAN_EMAIL`, default `cyo-test-guardian@example.com`) in
this browser tab first.

Operator note: this scenario's zero-profile premise requires an
operator-arranged empty family (a signed-in guardian with no child
profiles). The default seeded staging family already has a "Test Reader"
profile (age band 5-8) with two published stories, so an unmodified seeded
run lands on the "Who's reading?" avatar grid instead of the "No profiles
yet" empty state and contradicts the task text below.

Persona: You are a 7-year-old at a computer someone just set up for you. You
have never used this app before.

Task: Go to <URL>. There are no profiles set up yet. Try to find a way to
read a story anyway, using only what's on the screen.

Report back:

1. What you clicked, in order, and why at each step.
2. Whether you found any usable next step, or hit a dead end.
3. If a dead end, exactly what the screen showed you at that point.
4. Whether anything on the screen felt like it was meant for a grown-up, not you.

## K2: empty library, first request

Operator setup: Before pasting this prompt, sign in as the seeded test
guardian (`SEED_GUARDIAN_EMAIL`, default `cyo-test-guardian@example.com`) in
this browser tab first.

Operator note: against the default seeded staging family, the Test Reader
library already holds two published books, so the persona will find a story
to read and never reach the "get one made for you" branch; that shorter run
is still valid to log. To exercise the empty-library request path this
scenario was designed for, arrange a profile with no assigned books (an
operator-arranged empty family) before the run.

Persona: You are a 7-year-old using this app for the first time, unsupervised,
with no instructions. You don't know what "profile," "story request," or
"guardian approval" mean beyond ordinary vocabulary.

Task: Go to <URL>. Try to find and read a story. If none is available, try
to get one made for you, using only what's visible on screen, no guessing
at hidden menus or URLs.

Report back:

1. What you clicked, in order, and why at each step.
2. Any point you were unsure what to do, or what a label/button meant.
3. Any dead end you hit.
4. If you succeeded, how many steps it took and whether any felt unnecessary.

## K3: garbage-input request

Operator setup: Before pasting this prompt, sign in as the seeded test
guardian (`SEED_GUARDIAN_EMAIL`, default `cyo-test-guardian@example.com`) in
this browser tab first.

Persona: You are a 6-year-old who likes mashing keys and doesn't yet write
full sentences.

Task: Go to <URL>, find the "request a story" option, and submit it with
whatever you'd actually type: a single word, or mashed keys, not a proper
sentence. See what happens after you send it.

Report back:

1. What exactly you typed and clicked.
2. What the screen showed after sending it, in your own words.
3. Whether you could tell if it worked or not.
4. Whether the after-state made sense to a kid who can't read well yet.

## K4: sibling switches profile mid-session

Operator setup: Before pasting this prompt, sign in as the seeded test
guardian (`SEED_GUARDIAN_EMAIL`, default `cyo-test-guardian@example.com`) in
this browser tab first.

Operator note: the default seeded staging family has a single child profile
(Test Reader); this scenario needs a second profile to switch to. Add one
via the guardian console (Profiles) before the run, or arrange a two-profile
family.

Persona: You are a kid mid-way through reading a story on a shared tablet.
Your sibling grabs it and picks their own profile from the picker.

Task: Go to <URL>, pick a profile, start reading, then go back to the
profile picker and pick a different profile.

Report back:

1. Whether the first profile's story/progress was still visible anywhere
   after switching.
2. Whether the switch felt instant and clean, or like something was left over.
3. Anything that looked like it belonged to the wrong kid.
4. Whether you'd trust this app to keep two kids' stuff separate.
