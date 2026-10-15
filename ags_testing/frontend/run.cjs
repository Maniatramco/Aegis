// Resolve test dependencies from the existing frontend installation.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const frontend = path.resolve(__dirname, '../../ags_frontend');
const env = { ...process.env, NODE_PATH: [path.join(frontend, 'node_modules'), process.env.NODE_PATH].filter(Boolean).join(path.delimiter) };
const [mode, ...extra] = process.argv.slice(2);
let args;
if (mode === 'unit') {
  const files = fs.readdirSync(__dirname).filter(name => name.endsWith('.test.cjs')).sort().map(name => path.join(__dirname, name));
  args = ['--test', ...extra, ...files];
} else if (mode === 'e2e' || mode === 'screenshots') {
  const cli = require.resolve('@playwright/test/cli', { paths: [frontend] });
  const suites = mode === 'e2e' ? ['current-workspace.spec.ts', 'recovery.spec.ts', 'review-flow.spec.ts'] : ['current-workspace.spec.ts', '-g', 'current.screens.fit'];
  args = [cli, 'test', '--config', path.join(__dirname, 'playwright.config.ts'), ...suites, ...extra];
} else {
  console.error('Use unit, e2e or screenshots.');
  process.exit(2);
}
const result = spawnSync(process.execPath, args, { cwd: frontend, env, stdio: 'inherit' });
if (result.error) throw result.error;
process.exit(result.status ?? 1);
