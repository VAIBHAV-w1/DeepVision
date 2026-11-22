import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { parseArgs } from 'node:util';

const require = createRequire(import.meta.url);
const frontendDir = path.resolve(import.meta.dirname, '..');
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

const driveRoot = path.parse(frontendDir).root; // e.g. 'D:\\'
const driveLetter = driveRoot.slice(0, 2);      // e.g. 'D:'
const topSegment = frontendDir.slice(driveLetter.length).replace(/\\/g, '/').split('/').filter(Boolean)[0] || '';
const topPrefix = topSegment ? `/${topSegment}` : '/';

function hasUsableNativeRolldown() {
  if (process.platform !== 'win32') return true;
  if (process.env.NAPI_RS_FORCE_WASI === 'error') return false;
  try {
    require.resolve('@rolldown/binding-win32-x64-msvc');
    return true;
  } catch {
    return false;
  }
}

function installWindowsWasiPathShim() {
  const wasiMod = require('node:wasi');
  const OrigWASI = wasiMod.WASI;
  wasiMod.WASI = class DeepVisionPatchedWASI extends OrigWASI {
    constructor(opts = {}) {
      super({
        ...opts,
        preopens: {
          '/': driveRoot,
          ...(opts.preopens || {}),
        },
      });
    }
  };

  const wtMod = require('node:worker_threads');
  const OrigWorker = wtMod.Worker;
  wtMod.Worker = class DeepVisionPatchedWorker extends OrigWorker {
    constructor(filename, options = {}) {
      if (String(filename).includes('wasi-worker') && options?.workerData) {
        options = {
          ...options,
          workerData: {
            ...options.workerData,
            rootDir: '/',
            hostRoot: driveRoot,
          },
        };
      }
      super(filename, options);
    }
  };

  const toWasiPath = (val) => {
    if (typeof val !== 'string') return val;
    if (val.length >= 2 && val[1] === ':' && val.slice(0, 2).toUpperCase() === driveLetter.toUpperCase()) {
      const rest = val.slice(2).replace(/\\/g, '/');
      return rest.startsWith('/') ? rest : `/${rest}`;
    }
    return val;
  };

  const fromWasiPath = (val) => {
    if (typeof val !== 'string') return val;
    if (val.startsWith('/') && !val.startsWith('//') && !val.startsWith('\0')) {
      const baseClean = val.split('?')[0].split('#')[0];
      if ((topPrefix !== '/' && val.startsWith(topPrefix)) || fs.existsSync(`${driveLetter}${baseClean}`)) {
        return `${driveLetter}${val}`;
      }
    }
    return val;
  };

  const mapArrayStrings = (arr, fn) =>
    Array.isArray(arr) ? arr.map((x) => (typeof x === 'string' ? fn(x) : x)) : arr;

  const wrapCallback = (fn) => {
    return function (...args) {
      const mappedArgs = args.map((a) => (typeof a === 'string' ? fromWasiPath(a) : mapStringsDeep(a, fromWasiPath)));
      const res = fn.apply(this, mappedArgs);
      if (res && typeof res.then === 'function') {
        return res.then((r) => mapStringsDeep(r, toWasiPath));
      }
      return mapStringsDeep(res, toWasiPath);
    };
  };

  const mapStringsDeep = (obj, fn, seen = new WeakSet()) => {
    if (typeof obj === 'string') return fn(obj);
    if (!obj || typeof obj !== 'object') return obj;
    const proto = Object.getPrototypeOf(obj);
    if (proto !== Object.prototype && proto !== null && !Array.isArray(obj)) return obj;
    if (seen.has(obj)) return obj;
    seen.add(obj);
    if (Array.isArray(obj)) return obj.map((x) => mapStringsDeep(x, fn, seen));
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      out[k] = typeof v === 'function' ? wrapCallback(v) : mapStringsDeep(v, fn, seen);
    }
    return out;
  };

  const wrapPropGetter = (proto, prop, mapper) => {
    const desc = Object.getOwnPropertyDescriptor(proto, prop);
    if (desc && typeof desc.get === 'function') {
      Object.defineProperty(proto, prop, {
        ...desc,
        get() {
          return mapper(desc.get.call(this));
        },
      });
    }
  };

  const wasiEntry = path.join(frontendDir, 'node_modules/@rolldown/binding-wasm32-wasi/rolldown-binding.wasi.cjs');
  const binding = require(wasiEntry);

  for (const m of ['generate', 'write', 'scan']) {
    const orig = binding.BindingBundler.prototype[m];
    if (typeof orig === 'function') {
      binding.BindingBundler.prototype[m] = function (opts, ...rest) {
        return orig.call(this, mapStringsDeep(opts, toWasiPath), ...rest);
      };
    }
  }
  const origWatchFiles = binding.BindingBundler.prototype.getWatchFiles;
  if (typeof origWatchFiles === 'function') {
    binding.BindingBundler.prototype.getWatchFiles = function () {
      return mapArrayStrings(origWatchFiles.call(this), fromWasiPath);
    };
  }

  const origGetFacade = binding.BindingOutputChunk.prototype.getFacadeModuleId;
  binding.BindingOutputChunk.prototype.getFacadeModuleId = function () {
    return fromWasiPath(origGetFacade.call(this));
  };
  const origGetModIds = binding.BindingOutputChunk.prototype.getModuleIds;
  binding.BindingOutputChunk.prototype.getModuleIds = function () {
    return mapArrayStrings(origGetModIds.call(this), fromWasiPath);
  };
  const origGetMods = binding.BindingOutputChunk.prototype.getModules;
  binding.BindingOutputChunk.prototype.getModules = function () {
    const m = origGetMods.call(this);
    return m && Array.isArray(m.keys) ? { ...m, keys: mapArrayStrings(m.keys, fromWasiPath) } : m;
  };

  wrapPropGetter(binding.BindingRenderedChunk.prototype, 'facadeModuleId', fromWasiPath);
  wrapPropGetter(binding.BindingRenderedChunk.prototype, 'moduleIds', (arr) => mapArrayStrings(arr, fromWasiPath));
  wrapPropGetter(binding.BindingRenderedChunk.prototype, 'modules', (m) =>
    m && Array.isArray(m.keys) ? { ...m, keys: mapArrayStrings(m.keys, fromWasiPath) } : m
  );

  const pcProto = binding.BindingPluginContext.prototype;
  const origPcLoad = pcProto.load;
  pcProto.load = function (spec, sideEffects, pkgPath) {
    return origPcLoad.call(this, toWasiPath(spec), sideEffects, toWasiPath(pkgPath));
  };
  const origPcResolve = pcProto.resolve;
  pcProto.resolve = async function (spec, importer, extra) {
    const res = await origPcResolve.call(this, toWasiPath(spec), toWasiPath(importer), extra);
    return res && typeof res === 'object'
      ? { ...res, id: fromWasiPath(res.id), packageJsonPath: fromWasiPath(res.packageJsonPath) }
      : res;
  };
  const origPcEmit = pcProto.emitFile;
  pcProto.emitFile = function (file, assetFilename, fnSanitized) {
    return origPcEmit.call(this, mapStringsDeep(file, toWasiPath), assetFilename, fnSanitized);
  };
  const origPcEmitChunk = pcProto.emitChunk;
  pcProto.emitChunk = function (file) {
    return origPcEmitChunk.call(this, mapStringsDeep(file, toWasiPath));
  };
  const origPcModInfo = pcProto.getModuleInfo;
  pcProto.getModuleInfo = function (id) {
    return origPcModInfo.call(this, toWasiPath(id));
  };
  const origPcModIds = pcProto.getModuleIds;
  pcProto.getModuleIds = function () {
    return mapArrayStrings(origPcModIds.call(this), fromWasiPath);
  };
  const origPcWatch = pcProto.addWatchFile;
  pcProto.addWatchFile = function (file) {
    return origPcWatch.call(this, toWasiPath(file));
  };

  for (const ctxCls of [binding.BindingLoadPluginContext, binding.BindingTransformPluginContext]) {
    if (ctxCls?.prototype?.addWatchFile) {
      const origW = ctxCls.prototype.addWatchFile;
      ctxCls.prototype.addWatchFile = function (file) {
        return origW.call(this, toWasiPath(file));
      };
    }
  }
  if (binding.BindingChunkingContext?.prototype?.getModuleInfo) {
    const origCMI = binding.BindingChunkingContext.prototype.getModuleInfo;
    binding.BindingChunkingContext.prototype.getModuleInfo = function (id) {
      return origCMI.call(this, toWasiPath(id));
    };
  }
  if (binding.BindingModuleInfo?.prototype) {
    wrapPropGetter(binding.BindingModuleInfo.prototype, 'id', fromWasiPath);
    for (const p of ['importers', 'dynamicImporters', 'importedIds', 'dynamicallyImportedIds']) {
      wrapPropGetter(binding.BindingModuleInfo.prototype, p, (arr) => mapArrayStrings(arr, fromWasiPath));
    }
  }
}

if (!hasUsableNativeRolldown()) {
  installWindowsWasiPathShim();
}

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

