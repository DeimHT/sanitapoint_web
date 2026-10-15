const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/equipo.js', 'utf8');
function puesto(storage = new Map()) {
  const frames = [];
  const calls = [];
  const context = vm.createContext({
    localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) },
    api: { async post(url) { calls.push(url); } },
    document: {
      getElementById: () => null,
      createElement: () => ({ style: {} }),
      body: { appendChild: frame => frames.push(frame) },
    }
  });
  vm.runInContext(source + '; globalThis.equipo = equipoLocal;', context);
  return { context, equipo: context.equipo, frames, calls, storage };
}
(async () => {
  const a = puesto(), b = puesto();
  a.equipo.guardar({ impresora_automatica: '1', lector_modo: 'ninguno' });
  assert.equal(a.equipo.lector().modo, 'ninguno');
  assert.equal(b.equipo.lector().modo, 'teclado');
  assert.equal(b.equipo.leer().impresora_automatica, '0');
  assert.equal(puesto(a.storage).equipo.leer().impresora_automatica, '1');
  await a.equipo.imprimir('T000001');
  assert.equal(a.frames.length, 1);
  assert.equal(b.frames.length, 0);
  assert.equal(a.frames[0].src, '/api/ventas/T000001/imprimir');
  assert.deepEqual(a.calls, ['/api/ventas/T000001/imprimir']);
  a.context.api.post = async () => { throw new Error('Ticket no encontrado'); };
  await assert.rejects(() => a.equipo.imprimir('AJENO'), /Ticket no encontrado/);
  assert.equal(a.frames.length, 1, 'No print view after denied access');
  a.storage.set('sanitapoint.equipo', '{invalid');
  assert.equal(a.equipo.lector().modo, 'teclado');
  for (const file of ['config', 'historial', 'venta', 'usuarios', 'equipo']) {
    const html = fs.readFileSync(`app/templates/${file}.html`, 'utf8');
    for (const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(match[1], { filename: file });
  }
  console.log('Puestos aislados, persistencia local, impresion autorizada y scripts: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
