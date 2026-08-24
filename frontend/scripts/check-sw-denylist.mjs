// SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
//
// SPDX-License-Identifier: MIT

/**
 * Assert the navigate-fallback denylist actually reached the emitted service
 * worker.
 *
 * `src/pwa/navigateFallbackDenylist.ts` is unit-tested, but a unit test proves
 * only that the array is correct, never that Workbox was told about it. The
 * single line that connects them is the `navigateFallbackDenylist` option in
 * `vite.config.ts`. Delete that line and the unit tests still pass, `tsc -b`
 * still passes, the whole CI matrix stays green, and the emitted `sw.js`
 * silently goes back to claiming every navigation on the origin, which is
 * exactly the regression that shipped and reached a parent on staging.
 *
 * So this reads the patterns back out of the built artifact. It runs as
 * `postbuild`, which npm invokes automatically after `npm run build`, so every
 * existing build (CI, Docker image, local) is covered without a new CI job.
 *
 * Workbox writes the denylist into `sw.js` as verbatim regex literals, and a
 * minifier cannot rewrite a regex literal's source, so a literal string search
 * is a sound check.
 */

import { readFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const FRONTEND_ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const SOURCE = join(FRONTEND_ROOT, 'src', 'pwa', 'navigateFallbackDenylist.ts')
const SERVICE_WORKER = join(FRONTEND_ROOT, 'dist', 'sw.js')

/** The exported array's body, so comments and prose outside it are ignored. */
const ARRAY_BODY = /NAVIGATE_FALLBACK_DENYLIST[^=]*=\s*\[(?<body>[\s\S]*?)\n\]/
/** One regex literal per entry, anchored to the start of its own line. */
const PATTERN_LITERAL = /^\s*(?<literal>\/(?:[^/\\\n]|\\.)+\/[a-z]*)\s*,/gm

function fail(message) {
  console.error(`check-sw-denylist: ${message}`)
  process.exit(1)
}

function read(path, what) {
  try {
    // #ASSUME: security: detect-non-literal-fs-filename fires on the `path`
    // PARAMETER, which is as far as it looks; it does no dataflow, so it
    // cannot see that both call sites pass a module-level constant. SOURCE
    // and SERVICE_WORKER are `join()`ed off `import.meta.url` (lines 30-32)
    // and nothing here reads argv, env, stdin, or the network, so there is no
    // attacker-controlled component to traverse with.
    // #VERIFY: re-check if `read()` ever gains a caller whose path argument is
    // not a module-level constant.
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- both callers pass module constants
    return readFileSync(path, 'utf8')
  } catch (error) {
    fail(
      `cannot read ${what} at ${relative(FRONTEND_ROOT, path)} ` +
        `(${error.code ?? error.message}). Run \`npm run build\` first; ` +
        'this check runs as its postbuild step.'
    )
  }
}

const source = read(SOURCE, 'the denylist source')
const arrayMatch = source.match(ARRAY_BODY)

if (arrayMatch?.groups?.body === undefined) {
  fail(
    'could not find the NAVIGATE_FALLBACK_DENYLIST array in ' +
      `${relative(FRONTEND_ROOT, SOURCE)}. If the export was renamed or ` +
      'restructured, update this check with it.'
  )
}

const expected = [...arrayMatch.groups.body.matchAll(PATTERN_LITERAL)].map(
  (match) => match.groups.literal
)

// An extractor that finds nothing must fail, not pass. A checker that reports
// success on empty input reads as coverage while providing none.
if (expected.length === 0) {
  fail(
    `extracted 0 patterns from ${relative(FRONTEND_ROOT, SOURCE)}. The ` +
      'denylist is either empty or no longer written as regex literals, and ' +
      'either way this check can no longer verify anything.'
  )
}

const serviceWorker = read(SERVICE_WORKER, 'the built service worker')
const missing = expected.filter((pattern) => !serviceWorker.includes(pattern))

if (missing.length > 0) {
  fail(
    `${missing.length} of ${expected.length} denylist pattern(s) absent from ` +
      `${relative(FRONTEND_ROOT, SERVICE_WORKER)}: ${missing.join(', ')}\n` +
      '  The service worker will answer those paths with the SPA shell.\n' +
      '  Check that vite.config.ts still passes navigateFallbackDenylist ' +
      'to VitePWA.'
  )
}

console.log(
  `check-sw-denylist: all ${expected.length} pattern(s) present in ` +
    `${relative(FRONTEND_ROOT, SERVICE_WORKER)}`
)
