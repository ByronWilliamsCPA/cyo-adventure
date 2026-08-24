import js from '@eslint/js'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

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
    },
  }
)
