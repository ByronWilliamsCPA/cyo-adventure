import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

interface PlayerTracesFixture {
  traces: Array<{ story: unknown }>
}

/**
 * Loads the "Lantern Cave" storybook fixture shared by the reader e2e specs
 * (reader.spec.ts, reader-conflict.spec.ts, reader-reload-resume.spec.ts,
 * naive-user/naive-kid-misuse.spec.ts) from the canonical conformance fixture
 * at schema/conformance/player_traces.json, which is also used by the
 * backend test suite.
 */
export function loadLanternStory(): unknown {
  const raw = readFileSync(
    path.resolve(here, '../../../schema/conformance/player_traces.json'),
    'utf-8'
  )
  const parsed = JSON.parse(raw) as PlayerTracesFixture
  return parsed.traces[0].story
}
