/* ESLint for the frontend (npm run lint; CI runs it). Kept minimal: the
   recommended JavaScript, TypeScript and React hooks rules. */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended', 'plugin:react-hooks/recommended'],
  ignorePatterns: ['dist', '.prerender', 'node_modules', 'public', 'test-results', 'playwright-report'],
}
