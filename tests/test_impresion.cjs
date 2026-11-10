const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/impresion.js', 'utf8');
function ejecutar({ ancho = 576, falla = false } = {}) {
  const eventos = [], handlers = {}, imagenHandlers = {};
  let impresiones = 0;
  vm.runInNewContext(source, {
    document: { getElementById: () => ({
      complete: true, naturalWidth: ancho,
      dataset: { eventos: '/api/ventas/T1/impresion-eventos/' },
      addEventListener: (tipo, fn) => { imagenHandlers[tipo] = fn; },
    }) },
    window: { addEventListener: (tipo, fn) => { handlers[tipo] = fn; }, focus() {},
      print() { impresiones++; if (falla) throw new Error('Impresora'); } },
    fetch: (url, opciones) => { eventos.push(url.split('/').pop()); assert.equal(opciones.method, 'POST'); return Promise.resolve({ ok: true }); },
    console,
  });
  return { eventos, handlers, imagenHandlers, impresiones: () => impresiones };
}
const normal = ejecutar();
assert.deepEqual(normal.eventos, ['solicitada']);
normal.imagenHandlers.load();
assert.equal(normal.impresiones(), 1, 'Una imagen en cache no duplica la impresion');
normal.handlers.afterprint();
assert.deepEqual(normal.eventos, ['solicitada', 'dialogo_cerrado']);
const rota = ejecutar({ ancho: 0 });
assert.equal(rota.impresiones(), 0);
assert.deepEqual(rota.eventos, ['error']);
assert.deepEqual(ejecutar({ falla: true }).eventos, ['solicitada', 'error']);
console.log('Eventos de impresion, cierre y errores: OK');
