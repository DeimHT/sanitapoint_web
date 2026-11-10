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
  equipoLocal: { leer: () => ({ impresora_automatica: '0' }), async imprimir() { impresiones++; return { mensaje: 'Dialogo abierto' }; } },
  fmtMonto: n => '$' + n, refrescarStatusbar() {}, alert() {}, leerCedula() {},
});
const script = fs.readFileSync('app/templates/venta.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/cargarServicios\(\);\s*$/, '');
vm.runInContext(script, contexto);
(async () => {
  siguiente = { ticket: 'T1', servicio_nombre: 'Ducha', monto: 2000, estado_kame: 'ok', folio_kame: '456', kame_timbre_disponible: false, kame_error_documento: 'Timbre pendiente' };
  const automaticos = [];
  contexto.equipoLocal.imprimir = async ticket => {
    automaticos.push(ticket);
    throw new Error('Timbre pendiente en KAME');
  };
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.deepEqual(automaticos, ['T1'], 'Al vender recupera automaticamente el timbre pendiente del mismo ticket');
  assert.match(elemento('estado_impresion').textContent, /Timbre pendiente/);
  assert.equal(ventas, 1);
  assert.doesNotMatch(elemento('resultado').innerHTML, /btn_imprimir_boleta|Imprimir boleta/);
  assert.match(elemento('resultado').innerHTML, /Ver PDF/);
  assert.match(elemento('resultado').innerHTML, /Recuperar timbre e imprimir/);
  let completarImpresion;
  const tickets = [];
  contexto.equipoLocal.imprimir = ticket => {
    tickets.push(ticket);
    return new Promise(resolve => { completarImpresion = resolve; });
  };
  const boton = elemento('btn_recuperar_boleta');
  const recuperacion = contexto.recuperarEImprimirBoleta(boton);
  await contexto.recuperarEImprimirBoleta(boton);
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.deepEqual(tickets, ['T1'], 'Recupera solamente el ticket ya emitido');
  assert.equal(ventas, 1, 'Recuperar no registra otro cobro');
  completarImpresion({ venta: { ...siguiente, kame_timbre_disponible: true }, mensaje: 'Dialogo abierto' });
  await recuperacion;
  assert.match(elemento('resultado').innerHTML, /Timbre recuperado/);
  contexto.equipoLocal.imprimir = async () => { throw new Error('XML pendiente en KAME'); };
  await contexto.recuperarEImprimirBoleta(boton);
  assert.match(elemento('estado_impresion').textContent, /XML pendiente/);
  assert.equal(boton.disabled, false, 'Permite reintentar si KAME sigue sin entregar el XML');
  contexto.equipoLocal.imprimir = async () => { impresiones++; return { mensaje: 'Dialogo abierto' }; };
  siguiente = { ...siguiente, kame_timbre_disponible: true, kame_error_documento: '' };
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.equal(impresiones, 1, 'El timbre listo abre impresion incluso con el ajuste manual anterior');
  assert.doesNotMatch(elemento('resultado').innerHTML, /btn_imprimir_boleta|Imprimir boleta/);
  assert.match(elemento('resultado').innerHTML, /Ver PDF/);
  assert.match(elemento('resultado').innerHTML, /Timbre listo/);
  siguiente = { ...siguiente, ticket: 'T2', kame_timbre_disponible: false };
  let entregarTimbre;
  contexto.equipoLocal.imprimir = ticket => {
    assert.equal(ticket, 'T2');
    return new Promise(resolve => { entregarTimbre = resolve; });
  };
  const ventaConEspera = contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  const cobros = ventas;
  assert.equal(vm.runInContext('ventaEnCurso', contexto), true);
  await contexto.vender({ id: 1, nombre: 'Ducha', precio: 2000 }, null);
  assert.equal(ventas, cobros, 'Mantiene la venta ocupada mientras recupera e imprime');
  entregarTimbre({ venta: { ...siguiente, kame_timbre_disponible: true }, mensaje: 'Dialogo abierto' });
  await ventaConEspera;
  assert.match(elemento('estado_impresion').textContent, /Dialogo abierto/);
  assert.match(elemento('resultado').innerHTML, /Timbre listo/);
  assert.equal(vm.runInContext('ventaEnCurso', contexto), false);
  console.log('Impresion automatica y recuperacion del mismo ticket sin otro cobro: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
