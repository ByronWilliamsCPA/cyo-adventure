# CYO conventions (read before building)

CYO is the design system for a choose-your-own-adventure reading app for kids.
The look is a warm storybook: parchment surfaces, amber accents, ink text,
generous radii, soft shadows. Two audiences share it: a kid-facing reading
surface (large touch targets, playful) and a guardian console (denser, calmer).

## Setup

No provider or theme wrapper is required; every component is self-contained.
The one hard requirement is the stylesheet: without `styles.css` on the page,
components render as unstyled browser defaults. Load `styles.css` plus
`_ds_bundle.js`, then use `window.CYO.*`.

## Styling idiom

Components style themselves via props (see each component's documented prop
contract for the exact API, e.g. Button's `variant` and `size`, StatusBadge's
`status`). Their CSS class names are internal; never target or invent component
classes.

For your own layout glue (page shells, grids, spacing), write plain CSS or
inline styles using the token custom properties. The full set lives in
`tokens/`; the families and their real names:

- Surfaces and text: `--color-parchment`, `--color-parchment-dark`,
  `--color-parchment-deeper`, `--color-ink`, `--color-ink-secondary`,
  `--color-ink-muted`
- Accents: `--color-amber` (+ `-hover`, `-light`, `-subtle`), `--color-sky`
  (+ `-light`), `--color-forest` (+ `-light`)
- Semantic: `--color-error`, `--color-warning`, `--color-success`
  (each with a `-light` pair)
- Spacing scale: `--space-1` through `--space-16` (1, 2, 3, 4, 5, 6, 8, 10,
  12, 16)
- Type: `--font-serif` (story passages only), `--font-sans` (all UI chrome),
  `--font-mono`; sizes `--text-xs` through `--text-3xl`; weights
  `--weight-normal|medium|semibold|bold`; line heights
  `--leading-tight|normal|relaxed`
- Shape and depth: `--radius-sm|md|lg|xl|full`, `--shadow-sm|md|lg`
- Motion: `--duration-fast|normal|slow`, `--easing-default`

Rule of thumb: story content reads in serif (`PassageText` does this for
you); everything interactive or navigational is sans. Backgrounds are
parchment tones, never pure white.

## Where the truth lives

Read `styles.css` and its imports (`tokens/`, `_ds_bundle.css`) before
styling by hand, and `components/<group>/<Name>/<Name>.prompt.md` before
composing a component you have not used yet.

## Idiomatic example

```jsx
const { Button, ProgressBar } = window.CYO;

<div style={{ background: 'var(--color-parchment)', padding: 'var(--space-6)',
              borderRadius: 'var(--radius-lg)', display: 'grid',
              gap: 'var(--space-4)', justifyItems: 'center' }}>
  <ProgressBar value={40} label="Chapter 2 of 5" showLabel />
  <Button variant="primary" size="lg">Keep reading</Button>
</div>
```
