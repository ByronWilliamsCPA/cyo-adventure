# Guardian persona: naive-user Claude-for-Chrome prompts

## G1: first login, zero children

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
