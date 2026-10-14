const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const release = { version: '0.2.0', assetUrl: 'https://github.com/mdeloughry/azeroth-addons/releases/download/v0.2.0/azeroth-addons.zip', sha256: 'a'.repeat(64), notes: 'Notes' };
const available = { state: 'available', release, currentVersion: '0.1.9', automatic: true };
const flush = () => new Promise(resolve => setImmediate(resolve));

function harness() {
  const calls = [], toasts = [], timers = new Map();
  let serial = 0;
  const api = {
    checkPluginUpdate: async force => { calls.push(['check', force]); return available; },
    preparePluginUpdate: async version => { calls.push(['prepare', version]); return release; },
  };
  const host = { DeckyBackend: { call: async (...args) => { calls.push(args); } } };
  const context = vm.createContext({
    exports: {}, window: host,
    setInterval: fn => { const id = ++serial; timers.set(id, fn); return id; },
    clearInterval: id => timers.delete(id),
    setTimeout: fn => { const id = ++serial; timers.set(id, fn); return id; },
    clearTimeout: id => timers.delete(id),
    require: name => {
      if (name === '@decky/api') return { toaster: { toast: value => toasts.push(value) } };
      if (name === '@decky/ui') return { Navigation: { Navigate() {}, CloseSideMenus() {} } };
      if (name === 'react') return { useSyncExternalStore: (_subscribe, get) => get() };
      if (name === './api') return { api, errorMessage: value => value.message };
      if (name === './routes') return { TAB_ROUTES: { settings: '/azeroth/settings' } };
      throw new Error(name);
    },
  });
  const code = ts.transpileModule(fs.readFileSync('src/pluginUpdater.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInContext(code, context);
  return { updater: context.exports, api, host, calls, toasts, timers };
}

test('startup/polling check once per cycle; one notification per version; unload clears timers', async () => {
  const h = harness();
  const stop = h.updater.startPluginUpdater();
  await flush();
  assert.equal(h.toasts.length, 1);
  await h.updater.checkPluginUpdate();
  assert.equal(h.toasts.length, 1);
  h.api.checkPluginUpdate = async () => ({ ...available, release: { ...release, version: '0.3.0' } });
  await h.updater.checkPluginUpdate();
  assert.equal(h.toasts.length, 2);
  stop();
  assert.equal(h.timers.size, 0);
});

test('installs exact backend plan with checksum and UPDATE type; no success claim', async () => {
  const h = harness();
  await h.updater.checkPluginUpdate(true);
  await h.updater.installPluginUpdate();
  assert.equal(JSON.stringify(h.calls.at(-1)), JSON.stringify([
    'utilities/install_plugin', release.assetUrl, 'Azeroth Addons', '0.2.0', 'a'.repeat(64), 2,
  ]));
  assert.equal(h.updater.usePluginUpdater().requesting, true);
  assert.match(h.updater.usePluginUpdater().message, /Confirm/);
  const count = h.calls.length;
  await h.updater.installPluginUpdate();
  assert.equal(h.calls.length, count);
  for (const timer of h.timers.values()) timer();
  assert.equal(h.updater.usePluginUpdater().requesting, false);
});

test('loader bridge missing: manual fallback; error remains visible and retry enabled', async () => {
  const h = harness();
  h.host.DeckyBackend = undefined;
  await h.updater.checkPluginUpdate();
  await h.updater.installPluginUpdate();
  assert.match(h.updater.usePluginUpdater().message, /Install Plugin from URL/);
  assert.equal(h.updater.usePluginUpdater().requesting, false);
});

test('backend blocks busy or stale update before any installer request', async () => {
  const h = harness();
  h.api.preparePluginUpdate = async () => { throw new Error('Wait for addon operations'); };
  await h.updater.checkPluginUpdate();
  await h.updater.installPluginUpdate();
  assert.match(h.updater.usePluginUpdater().message, /Wait for addon operations/);
  assert.equal(h.calls.some(call => call[0] === 'utilities/install_plugin'), false);
});

test('unload ignores an in-flight release response and notification', async () => {
  const h = harness();
  let resolve;
  h.api.checkPluginUpdate = () => new Promise(done => { resolve = done; });
  const stop = h.updater.startPluginUpdater();
  stop();
  resolve(available);
  await flush();
  assert.equal(h.updater.usePluginUpdater().status, null);
  assert.equal(h.toasts.length, 0);
});

test('only available releases notify; offline checks do not throw', async () => {
  const h = harness();
  for (const state of ['disabled', 'up-to-date', 'error']) {
    h.api.checkPluginUpdate = async () => ({ ...available, state, release: null });
    await h.updater.checkPluginUpdate();
  }
  assert.equal(h.toasts.length, 0);
  h.api.checkPluginUpdate = async () => { throw new Error('Backend starting'); };
  await h.updater.checkPluginUpdate();
  assert.equal(h.updater.usePluginUpdater().checking, false);
  assert.match(h.updater.usePluginUpdater().message, /Backend starting/);
});
