const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let expire, cleared = 0, calls = 0, timeoutMs;
const context = vm.createContext({
  AbortController,
  setTimeout(fn, ms) { timeoutMs = ms; expire = fn; return 1; },
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
  assert.equal(timeoutMs, 210000, 'La venta admite autenticacion, emision y recuperacion del XML por 120 segundos');
  expire();
  await assert.rejects(request, error => error.resultadoIncierto && /puede haberse registrado/.test(error.message));
  assert.equal(calls, 1, 'Aborting a sale must never retry it');
  assert.equal(cleared, 1);
  context.fetch = async () => ({ ok: true, status: 200, json: async () => ({ ticket: 'T1' }) });
  const result = await context.client.post('/api/ventas', {});
  assert.equal(result.ticket, 'T1');
  assert.equal(cleared, 2);
  await context.client.post('/api/ventas/T1/imprimir', {});
  assert.equal(timeoutMs, 150000, 'La recuperacion desde Imprimir admite los 120 segundos del servidor');
  await context.client.post('/api/caja/abrir', {});
  assert.equal(timeoutMs, 60000, 'Los otros POST conservan su espera habitual');
  await context.client.post('/api/ventas', {}, { timeoutMs: 5000 });
  assert.equal(timeoutMs, 5000, 'Una espera explicita conserva prioridad');
  assert.equal(cleared, 5);
  console.log('Esperas coordinadas de venta/impresion, limpieza y ausencia de reintentos POST: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
