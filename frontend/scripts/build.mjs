import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { parseArgs } from 'node:util';
import { frontendDir, ensureWindowsRolldownCompat } from './wasi-shim.mjs';

const require = createRequire(import.meta.url);
process.chdir(frontendDir);

const { values: cli } = parseArgs({
  options: {
    outDir: { type: 'string' },
    base: { type: 'string' },
    mode: { type: 'string' },
    emptyOutDir: { type: 'string' },
    sourcemap: { type: 'boolean' },
  },
  strict: false,
});

ensureWindowsRolldownCompat();

let canLightningCss = true;
try {
  require(path.join(frontendDir, 'node_modules/lightningcss'));
} catch {
  canLightningCss = false;
}

const viteEntry = pathToFileURL(path.join(frontendDir, 'node_modules/vite/dist/node/index.js')).href;
const { build } = await import(viteEntry);

const buildOverrides = {};
if (cli.outDir) buildOverrides.outDir = cli.outDir;
if (cli.emptyOutDir !== undefined) buildOverrides.emptyOutDir = cli.emptyOutDir !== 'false';
if (cli.sourcemap !== undefined) buildOverrides.sourcemap = cli.sourcemap;
if (!canLightningCss) buildOverrides.cssMinify = false;

await build({
  root: frontendDir,
  configFile: path.join(frontendDir, 'vite.config.js'),
  ...(cli.mode ? { mode: cli.mode } : {}),
  ...(cli.base ? { base: cli.base } : {}),
  ...(Object.keys(buildOverrides).length > 0 ? { build: buildOverrides } : {}),
});
