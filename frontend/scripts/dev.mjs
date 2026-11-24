import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { frontendDir, ensureWindowsRolldownCompat } from './wasi-shim.mjs';

process.chdir(frontendDir);

const rawArgs = process.argv.slice(2);
const getArgValue = (name) => {
  const eqPrefix = `--${name}=`;
  for (let i = 0; i < rawArgs.length; i++) {
    const arg = rawArgs[i];
    if (arg.startsWith(eqPrefix)) return arg.slice(eqPrefix.length);
    if (arg === `--${name}`) {
      const next = rawArgs[i + 1];
      if (next && !next.startsWith('-')) return next;
      return '';
    }
  }
  return undefined;
};

ensureWindowsRolldownCompat();

const viteEntry = pathToFileURL(path.join(frontendDir, 'node_modules/vite/dist/node/index.js')).href;
const { createServer } = await import(viteEntry);

const serverOverrides = {};
const hostArg = getArgValue('host');
if (hostArg !== undefined) {
  serverOverrides.host = hostArg === '' ? true : hostArg;
}
const portArg = getArgValue('port');
if (portArg) {
  const parsedPort = Number(portArg);
  if (Number.isFinite(parsedPort) && parsedPort > 0) {
    serverOverrides.port = parsedPort;
  }
}
if (rawArgs.includes('--strictPort')) {
  serverOverrides.strictPort = true;
}
if (rawArgs.includes('--open')) {
  serverOverrides.open = true;
}
const modeArg = getArgValue('mode');

const server = await createServer({
  root: frontendDir,
  configFile: path.join(frontendDir, 'vite.config.js'),
  ...(modeArg ? { mode: modeArg } : {}),
  ...(Object.keys(serverOverrides).length > 0 ? { server: serverOverrides } : {}),
});

await server.listen();
server.printUrls();
server.bindCLIShortcuts({ print: true });
