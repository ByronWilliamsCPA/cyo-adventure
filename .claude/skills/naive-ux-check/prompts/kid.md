# Kid persona: naive-user Claude-for-Chrome prompts

Paste one block below into the Claude-for-Chrome extension at a time. After
each run, log the response via the naive-ux-check skill (see SKILL.md).

## K1: cold start, zero profiles

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
