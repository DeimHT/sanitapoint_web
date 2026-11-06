const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let expire, cleared = 0, calls = 0;
const context = vm.createContext({
  AbortController,
  setTimeout(fn, ms) { assert.equal(ms, 60000); expire = fn; return 1; },
  clearTimeout() { cleared++; },
  fetch(path, options) {
    calls++;
    return new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new Error('aborted')));
    });
  },
});
vm.runInContext(fs.readFileSync('app/static/js/api.js', 'utf8').split('function fmtMonto')[0] + ';globalThis.client = api;', context);
(async () => {
  const request = context.client.post('/api/ventas', { servicio_id: 1 });
  expire();
  await assert.rejects(request, error => error.resultadoIncierto && /puede haberse registrado/.test(error.message));
  assert.equal(calls, 1, 'Aborting a sale must never retry it');
  assert.equal(cleared, 1);
  context.fetch = async () => ({ ok: true, status: 200, json: async () => ({ ticket: 'T1' }) });
  const result = await context.client.post('/api/ventas', {});
  assert.equal(result.ticket, 'T1');
  assert.equal(cleared, 2);
  console.log('POST timeout, cleanup and no automatic retries: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
