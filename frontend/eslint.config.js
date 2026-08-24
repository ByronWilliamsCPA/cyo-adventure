import js from '@eslint/js'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import globals from 'globals'
import noUnsanitized from 'eslint-plugin-no-unsanitized'
import security from 'eslint-plugin-security'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// eslint-plugin-security rules held OFF rather than raised to 'error'.
//
// Each was measured against this codebase on 2026-08-24, not judged by
// reputation: with all 14 rules at 'error' the tree produced 74 findings, and
// every one was a false positive. The two below accounted for 68 of them and
// are structurally unable to be right here, so they are disabled with the
// evidence rather than suppressed 68 times at the call sites.
//
// The other 12 rules stay at 'error'. Two of them (detect-unsafe-regex,
// detect-non-literal-regexp) do fire, and are handled where they fire: by one
// inline disable carrying a measurement, and by the test-file override below.
// The remaining 10 find nothing today and cost nothing to keep armed.
//
// Read this as a statement about the tool, not about the code: a lint-grade
// pattern matcher found zero real defects in ~80k lines. It is a floor under
// the SAST gap, not a substitute for a dataflow engine.
const SECURITY_RULES_OFF = new Set([
  // Fires on EVERY computed member access, including `STATUS_LABELS[status]`
  // and `change.payload[key]`. 64 of the 74 findings, all idiomatic TypeScript
  // lookups whose key types the compiler already constrains. Real prototype
  // pollution needs dataflow to distinguish an attacker-controlled key from a
  // local one, which this rule does not do and Semgrep does.
  'security/detect-object-injection',
  // Matches on IDENTIFIER NAME, not on the comparison. Both src/ hits are
  // `token === null`, a null check: notificationsStream.ts:81 and
  // useApi.ts:153. Beyond the false positives, a timing attack against a
  // string compare inside the browser has no threat model, since the attacker
  // running it already controls that browser.
  'security/detect-possible-timing-attacks',
])

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'src/client'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        // projectService discovers the right tsconfig per file by walking
        // the project reference graph rooted at tsconfig.json (app, node,
        // e2e), so src/, e2e/, and e2e-real/ are all type-aware without
        // listing every tsconfig explicitly.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'jsx-a11y': jsxA11y,
      security,
      'no-unsanitized': noUnsanitized,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // A horizontally-scrollable region (legal/PrivacyPolicyPage.tsx's
      // table wrappers) needs tabIndex=0 on its role="region" container so
      // keyboard users can scroll it (WAI-ARIA APG SCR26); this rule's
      // `roles`/`tags` options have no default list at all (verified against
      // 6.10.2's source: unset, they're simply never checked), so this
      // project-wide allowance is filling an absent exception list, not
      // widening an existing one.
      'jsx-a11y/no-noninteractive-tabindex': ['error', { roles: ['region'] }],

      // SAST floor for the TypeScript tree. CodeQL default setup is disabled
      // on a cost rationale, Bandit is Python-only and OSV-Scanner is
      // dependency SCA, so before these rules nothing statically analysed
      // frontend/ at all.
      //
      // Severity is pinned to 'error' DELIBERATELY and must stay that way.
      // eslint-plugin-security ships all 14 of its rules at 'warn', and the
      // lint step in ci.yml runs `npm run lint` without --max-warnings=0, so
      // ESLint exits 0 on warnings. Spreading the plugin's recommended config
      // would therefore have added a security scanner that cannot fail a
      // build. Do not relax any of these to 'warn' without also making the CI
      // lint step fail on warnings.
      //
      // no-unsanitized ships at 'error' already; it is listed explicitly
      // rather than spread so that the severity is visible at the call site
      // and survives an upstream default change.
      'no-unsanitized/method': 'error',
      'no-unsanitized/property': 'error',
      ...Object.fromEntries(
        Object.keys(security.configs.recommended.rules)
          .filter((rule) => !SECURITY_RULES_OFF.has(rule))
          .map((rule) => [rule, 'error'])
      ),
    },
  },
  {
    // Test and end-to-end code builds RegExps out of fixture strings it owns
    // (`new RegExp(profileName)`), which is what detect-non-literal-regexp is
    // for in production code and noise here: there is no untrusted input and
    // no shipped surface. All 5 of its findings were in these paths and none
    // in application source, so the rule stays at 'error' everywhere it could
    // actually matter.
    files: [
      'e2e/**/*.{ts,tsx}',
      'e2e-real/**/*.{ts,tsx}',
      'e2e-prod/**/*.{ts,tsx}',
      'e2e-staging/**/*.{ts,tsx}',
      'e2e-staging-sweep/**/*.{ts,tsx}',
      'e2e-support/**/*.{ts,tsx}',
      'src/test/**/*.{ts,tsx}',
      'src/**/*.test.{ts,tsx}',
    ],
    rules: {
      'security/detect-non-literal-regexp': 'off',
    },
  }
)
