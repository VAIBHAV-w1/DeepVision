import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
export const frontendDir = path.resolve(import.meta.dirname, '..');

const driveRoot = path.parse(frontendDir).root; // e.g. 'D:\\'
const driveLetter = driveRoot.slice(0, 2);      // e.g. 'D:'
const topSegment = frontendDir.slice(driveLetter.length).replace(/\\/g, '/').split('/').filter(Boolean)[0] || '';
const topPrefix = topSegment ? `/${topSegment}` : '/';

export function hasUsableNativeRolldown() {
  if (process.platform !== 'win32') return true;
  if (process.env.NAPI_RS_FORCE_WASI === 'error') return false;
  try {
    require.resolve('@rolldown/binding-win32-x64-msvc');
    return true;
  } catch {
    return false;
  }
}

export function installWindowsWasiPathShim() {
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

  // Patch ResolverFactory & resolve/transform helpers for Vite dev server on Windows WASI
  const rfProto = binding.ResolverFactory?.prototype;
  if (rfProto) {
    for (const syncMethod of ['sync', 'resolveFileSync', 'resolveDtsSync']) {
      const orig = rfProto[syncMethod];
      if (typeof orig === 'function') {
        rfProto[syncMethod] = function (dirOrFile, spec, ...rest) {
          const res = orig.call(this, toWasiPath(dirOrFile), toWasiPath(spec), ...rest);
          return mapStringsDeep(res, fromWasiPath);
        };
      }
    }
    for (const asyncMethod of ['async', 'resolveFileAsync', 'resolveDtsAsync']) {
      const orig = rfProto[asyncMethod];
      if (typeof orig === 'function') {
        rfProto[asyncMethod] = async function (dirOrFile, spec, ...rest) {
          const res = await orig.call(this, toWasiPath(dirOrFile), toWasiPath(spec), ...rest);
          return mapStringsDeep(res, fromWasiPath);
        };
      }
    }
    if (typeof rfProto.cloneWithOptions === 'function') {
      const origClone = rfProto.cloneWithOptions;
      rfProto.cloneWithOptions = function (opts) {
        return origClone.call(this, mapStringsDeep(opts, toWasiPath));
      };
    }
    const OrigResolverFactory = binding.ResolverFactory;
    binding.ResolverFactory = new Proxy(OrigResolverFactory, {
      construct(target, args, newTarget) {
        const mappedArgs = args.map((a) => mapStringsDeep(a, toWasiPath));
        return Reflect.construct(target, mappedArgs, newTarget);
      },
    });
  }

  for (const syncFn of ['resolveTsconfig']) {
    const orig = binding[syncFn];
    if (typeof orig === 'function') {
      binding[syncFn] = (p, ...rest) => mapStringsDeep(orig(toWasiPath(p), ...rest), fromWasiPath);
    }
  }

  // Patch BindingCallableBuiltinPlugin (used by Vite 8 dev server's builtin viteResolvePlugin)
  const callableProto = binding.BindingCallableBuiltinPlugin?.prototype;
  if (callableProto) {
    const origResolveId = callableProto.resolveId;
    if (typeof origResolveId === 'function') {
      callableProto.resolveId = async function (id, importer, opts, ...rest) {
        const cleanRawId = typeof id === 'string' ? id.replace(/\\/g, '/') : id;
        const feNorm = frontendDir.replace(/\\/g, '/');
        const idForWasi = (typeof cleanRawId === 'string' && cleanRawId.toLowerCase().startsWith((feNorm + '/').toLowerCase()))
          ? cleanRawId.slice(feNorm.length)
          : toWasiPath(id);
        let res = await origResolveId.call(
          this,
          idForWasi,
          toWasiPath(importer),
          mapStringsDeep(opts, toWasiPath),
          ...rest
        );
        if (!res && typeof cleanRawId === 'string' && /^[A-Za-z]:\//.test(cleanRawId) && !/\.html(?:$|\?)/i.test(cleanRawId)) {
          const [baseFile, ...qParts] = cleanRawId.split('?');
          if (fs.existsSync(baseFile) && fs.statSync(baseFile).isFile()) {
            res = { id: qParts.length ? `${baseFile}?${qParts.join('?')}` : baseFile };
          }
        }
        return mapStringsDeep(res, fromWasiPath);
      };
    }
    const origLoad = callableProto.load;
    if (typeof origLoad === 'function') {
      callableProto.load = async function (id, ...rest) {
        const res = await origLoad.call(this, toWasiPath(id), ...rest);
        return mapStringsDeep(res, fromWasiPath);
      };
    }
    const origTransform = callableProto.transform;
    if (typeof origTransform === 'function') {
      callableProto.transform = async function (code, id, ...rest) {
        const res = await origTransform.call(this, code, toWasiPath(id), ...rest);
        return mapStringsDeep(res, fromWasiPath);
      };
    }
    const origWatchChange = callableProto.watchChange;
    if (typeof origWatchChange === 'function') {
      callableProto.watchChange = function (id, event, ...rest) {
        return origWatchChange.call(this, toWasiPath(id), event, ...rest);
      };
    }
    const OrigCallable = binding.BindingCallableBuiltinPlugin;
    binding.BindingCallableBuiltinPlugin = new Proxy(OrigCallable, {
      construct(target, args, newTarget) {
        const rawBinding = args[0];
        const origOpts = rawBinding?.options;
        if (origOpts && (typeof origOpts === 'object' || typeof origOpts === 'function')) {
          rawBinding.options = new Proxy(origOpts, {
            get(optTarget, key, receiver) {
              const val = Reflect.get(optTarget, key, receiver);
              if (typeof val === 'function') return wrapCallback(val);
              return mapStringsDeep(val, toWasiPath);
            },
          });
        }
        return Reflect.construct(target, args, newTarget);
      },
    });
  }
}

export function ensureWindowsRolldownCompat() {
  if (!hasUsableNativeRolldown()) {
    installWindowsWasiPathShim();
  }
}
