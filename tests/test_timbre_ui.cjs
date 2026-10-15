const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elementos = new Map();
function elemento(id) {
  if (!elementos.has(id)) elementos.set(id, {
    disabled: false, textContent: '', innerHTML: '', children: [],
    setAttribute() {}, addEventListener() {}, replaceChildren() { this.children = []; },
    appendChild(hijo) { this.children.push(hijo); },
    classList: { add() {}, remove() {}, toggle() {} },
  });
  return elementos.get(id);
}
let siguiente, impresiones = 0, ventas = 0;
const contexto = vm.createContext({
  document: { getElementById: elemento, querySelectorAll: () => [], createElement: () => elemento('aviso') },
  api: { async post() { ventas++; return siguiente; } },
  equipoLocal: { leer: () => ({ impresora_automatica: '1' }), async imprimir() { impresiones++; return { mensaje: 'Dialogo abierto' }; } },
  fmtMonto: n => '$' + n, refrescarStatusbar() {}, alert() {}, leerCedula() {},
});
const script = fs.readFileSync('app/templates/venta.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/cargarServicios\(\);\s*$/, '');
vm.runInContext(script, contexto);
(async () => {
  siguiente = { ticket: 'T1', servicio_nombre: 'Ducha', monto: 2000, estado_kame: 'ok', folio_kame: '456', kame_timbre_disponible: false, kame_error_documento: 'Timbre pendiente' };
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.equal(impresiones, 0, 'Una boleta real sin timbre no se imprime automaticamente');
  assert.match(elemento('resultado').innerHTML, /Timbre pendiente/);
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.equal(ventas, 1, 'Una boleta incompleta bloquea el siguiente cobro');
  await elemento('btn_imprimir_boleta').onclick.call(elemento('btn_imprimir_boleta'));
  assert.equal(impresiones, 1);
  assert.equal(ventas, 1, 'Reintentar imprimir no crea otra venta');
  siguiente = { ...siguiente, kame_timbre_disponible: true, kame_error_documento: '' };
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.equal(impresiones, 2, 'El timbre listo permite impresion automatica');
  assert.match(elemento('resultado').innerHTML, /Timbre listo/);
  console.log('Impresion automatica con timbre y reintento sin nueva venta: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
