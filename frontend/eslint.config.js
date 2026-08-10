import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // eslint-plugin-react-hooks v7's "recommended" config bundles React
      // Compiler-oriented rules (set-state-in-effect, immutability, purity)
      // on top of the classic rules-of-hooks/exhaustive-deps checks. This
      // codebase doesn't use the React Compiler and relies throughout on
      // ordinary patterns (fetch-in-effect, functions referenced via closure
      // before their declaration line) that those rules flag as hard errors.
      // Keep them visible as warnings without failing CI/local lint.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
])
