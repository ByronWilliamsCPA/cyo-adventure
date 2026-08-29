import path from 'node:path'

/**
 * Resolves where the staging tier's Playwright `storageState` files live for
 * each seeded role, and is the single source of truth both configs and the
 * setup spec import from, so the write side (`e2e-staging/auth.setup.ts`) and
 * every read side (the tier's spec files, plus the separate sweep config's
 * own `npm run` invocation) can never drift onto different paths.
 *
 * #CRITICAL: security: each file this resolves to holds a live staging bearer
 * token (see `e2e-staging/auth.setup.ts`), and this repo is public.
 * #VERIFY: the directory this resolves into (`.auth/`, sibling to this file's
 * parent) is covered by `frontend/.gitignore`'s
 * `e2e-staging/.auth/` entry, and is NOT under `frontend/test-results/`, the
 * one directory `.github/workflows/e2e-staging.yml` uploads wholesale as a
 * Playwright-failure artifact.
 *
 * Resolved from this module's own location with `import.meta.dirname` rather
 * than a bare relative string. Verified directly against this repo's
 * installed Playwright (a throwaway config in a nested directory, one
 * `storageState: 'x.json'` string, and two probe runs): a relative
 * `storageState` string is passed straight to `fs.readFile` with no
 * config-relative resolution at all, so it resolves against `process.cwd()`,
 * the same as any other relative path in Node. This differs from
 * `e2e-staging/support/device-grant.ts`'s `LEAK_LOG_PATH` comment, which
 * documents `outputDir` (a path Playwright's config loader does specially
 * resolve against the config file's directory): `storageState` gets no such
 * treatment. `process.cwd()` and this file's directory only coincide when a
 * tier is launched from `frontend/` (which both `npm run test:e2e:staging`
 * and `npm run test:e2e:staging:sweep` do, via the workflow's
 * `working-directory: ./frontend`); an absolute path derived from this file's
 * own known location is correct regardless of which shell or cwd invoked it.
 */
export function stagingStorageStatePath(role: 'guardian' | 'admin'): string {
  return path.resolve(import.meta.dirname, '../.auth', `${role}.json`)
}
