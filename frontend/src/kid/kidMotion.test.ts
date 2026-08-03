import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/**
 * Reduce-motion coverage for the kid shell, asserted against the stylesheet
 * text itself.
 *
 * jsdom never applies these rules (vitest stubs CSS imports), so no rendering
 * test can reach them, and a motion declaration that no reduce-motion path
 * neutralises is invisible to every other test in this repo. That is exactly
 * how `.weekly-ring svg circle`'s stroke-dashoffset transition shipped
 * uncovered while the celebrate animation beside it was stilled twice over.
 *
 * The two paths are NOT redundant. `@media (prefers-reduced-motion: reduce)`
 * carries the OS-level preference; `[data-reduce-motion='true']` carries the
 * guardian's per-profile `reduce_motion` flag, stamped on the kid shell, for a
 * child whose device preference is unset but whose guardian asked for stillness
 * anyway. Covering one and not the other silently drops half the audience.
 */
const here = path.dirname(fileURLToPath(import.meta.url))
const css = readFileSync(path.resolve(here, 'kid.css'), 'utf-8')

/** The `@media (prefers-reduced-motion: reduce)` block bodies, concatenated. */
function osReduceMotionBlocks(source: string): string {
  const bodies: string[] = []
  const opener = '@media (prefers-reduced-motion: reduce) {'
  let from = source.indexOf(opener)
  while (from !== -1) {
    // Brace-count to the block's own close, so a nested rule's `}` does not
    // truncate the body and let an assertion pass against half a block.
    let depth = 0
    let cursor = from + opener.length - 1
    const start = cursor + 1
    for (; cursor < source.length; cursor += 1) {
      if (source[cursor] === '{') depth += 1
      else if (source[cursor] === '}') {
        depth -= 1
        if (depth === 0) break
      }
    }
    bodies.push(source.slice(start, cursor))
    from = source.indexOf(opener, cursor)
  }
  return bodies.join('\n')
}

const osBlock = osReduceMotionBlocks(css)

describe('kid.css reduce-motion coverage', () => {
  it('finds at least one OS-level reduce-motion block to assert against', () => {
    // Guards the parser, not the stylesheet: every assertion below is a
    // substring check, and a parser that silently returned '' would make all
    // of them vacuously... fail, but for the wrong reason. This names the
    // cause instead.
    expect(osBlock.length).toBeGreaterThan(0)
  })

  it('stills the weekly ring progress transition under the OS preference', () => {
    expect(osBlock).toMatch(/\.weekly-ring svg circle\s*\{\s*transition:\s*none/)
  })

  it('stills the weekly ring progress transition under the guardian flag', () => {
    expect(css).toMatch(
      /\[data-reduce-motion='true'\] \.weekly-ring svg circle\s*\{\s*transition:\s*none/
    )
  })

  it('stills the weekly ring celebrate animation under both paths', () => {
    // The half that already worked. Kept so a fix to the transition cannot be
    // made by moving the animation rule around, and so the pairing itself is
    // the thing under test rather than one selector.
    expect(osBlock).toMatch(/\.weekly-ring--celebrate svg\s*\{\s*animation:\s*none/)
    expect(css).toMatch(
      /\[data-reduce-motion='true'\] \.weekly-ring--celebrate svg\s*\{\s*animation:\s*none/
    )
  })

  it('stills the picker "new story!" pill under both paths', () => {
    // Bounded to two iterations (4.8s) as its primary WCAG 2.2.2 answer, since
    // the picker route carries no profile and therefore no data-reduce-motion
    // attribute. Both paths are still declared, and this pins them: the pill's
    // own comment explains the bound, and a later edit that raises the
    // iteration count would make these rules load-bearing again.
    expect(osBlock).toMatch(/\.picker-tile__new-pill\s*\{\s*animation:\s*none/)
    expect(css).toMatch(
      /\[data-reduce-motion='true'\] \.picker-tile__new-pill\s*\{\s*animation:\s*none/
    )
  })
})
