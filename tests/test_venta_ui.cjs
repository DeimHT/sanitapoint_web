const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    disabled: false, textContent: id, attributes: {}, children: [],
    setAttribute(k, v) { this.attributes[k] = v; },
    addEventListener() {}, replaceChildren() { this.children = []; },
    appendChild(child) { this.children.push(child); },
    querySelector() { return element('elegir_persona'); },
    classList: { add() {}, remove() {}, toggle() {} },
  });
  return elements.get(id);
}
const button = element('servicio');
const payment = element('pago');
const pass = element('btn_pase');
const script = fs.readFileSync('app/templates/venta.html', 'utf8')
  .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/cargarServicios\(\);\s*$/, '');
let calls = 0;
let resolveRequest, rejectRequest;
const context = vm.createContext({
  document: {
    getElementById: element,
    querySelectorAll: selector => selector.includes('#grid_servicios') ? [button, payment, pass] : [],
    createElement: () => element('aviso'),
  },
  api: { post() { calls++; return new Promise((resolve, reject) => {
    resolveRequest = resolve; rejectRequest = reject;
  }); } },
  fmtMonto: value => '$' + value, refrescarStatusbar() {}, alert() {},
  leerCedula: require('../app/static/js/cedula.js').leerCedula,
});
vm.runInContext(script, context);
context.service = { id: 1, nombre: 'Baño', precio: 500 };
context.button = button;
(async () => {
  const first = vm.runInContext('vender(service, button)', context);
  const repeated = vm.runInContext('vender(service, button)', context);
  assert.equal(calls, 1, 'Repeated click must not send another sale');
  assert.equal(button.textContent, 'Procesando…');
  assert.ok(button.disabled && payment.disabled && pass.disabled);
  assert.match(element('resultado').children[0].textContent, /Procesando/);
  resolveRequest({ servicio_nombre: 'Baño', monto: 500, ticket: 'T1', estado_kame: 'mock' });
  await Promise.all([first, repeated]);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'servicio');
  const failed = vm.runInContext('vender(service, button)', context);
  rejectRequest(new Error('Sin conexión'));
  await failed;
  assert.equal(calls, 2);
  assert.equal(button.disabled, false, 'Buttons must recover after an error');
  assert.match(element('resultado').innerHTML, /Sin conexión/);
  vm.runInContext('usuarios = [{id: 2, nombre: "Persona", rut: "12.345.678-5"}]', context);
  element('pase_lectura').value = 'https://example.test/?RUN=12345678-5';
  vm.runInContext('buscarPaseEscaneado()', context);
  assert.match(element('pase_lectura_estado').textContent, /Persona encontrada/);
  assert.equal(element('pase_lectura').value, 'https://example.test/?RUN=12345678-5', 'The scanned or pasted URL must remain available for review');
  vm.runInContext('buscarPaseEscaneado()', context);
  assert.match(element('pase_lectura_estado').textContent, /Persona encontrada/, 'Reviewing again must not produce an empty-reading error');
  assert.equal(element('pase_lectura_persona').children.length, 1);
  assert.equal(calls, 2, 'Scanning identifies the person without issuing a pass before selection');
  vm.runInContext('usuarios = []', context);
  element('pase_lectura').value = 'https://example.test/?RUN=12345678-5';
  vm.runInContext('buscarPaseEscaneado()', context);
  assert.match(element('pase_lectura_estado').textContent, /no está registrada/);
  assert.equal(element('pase_lectura_persona').children.length, 0);
  console.log('Sale feedback and repeated-click protection: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
