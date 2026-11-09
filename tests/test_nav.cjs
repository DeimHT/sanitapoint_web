const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/api.js', 'utf8');
const casos = [
  ['cajero', ['emitir_boletas', 'caja_apertura', 'caja_cierre'], ['venta', 'caja']],
  ['supervisor', ['caja_retiro', 'ver_historial', 'config_equipo'], ['caja', 'historial', 'equipo']],
  ['contabilidad', ['ver_reportes', 'ver_cierres', 'ver_historial', 'gestionar_cuentas', 'config_equipo'], ['historial', 'cierres', 'reportes', 'cuentas', 'equipo']],
  ['administrador', ['emitir_boletas', 'caja_apertura', 'ver_historial', 'ver_cierres', 'gestionar_clientes', 'ver_reportes', 'configuracion', 'gestionar_cuentas', 'config_equipo'], ['venta', 'caja', 'historial', 'cierres', 'clientes', 'reportes', 'config', 'cuentas', 'equipo']],
];
(async () => {
  for (const [rol, caps, esperados] of casos) {
    const enlaces = ['venta', 'caja', 'historial', 'cierres', 'clientes', 'reportes', 'config', 'cuentas', 'equipo'].map(clave => ({ dataset: { nav: clave }, hidden: true }));
    const context = vm.createContext({
      fetch: async () => ({ ok: true, json: async () => ({ rol, caps }) }),
      document: { addEventListener() {}, getElementById: () => null, querySelectorAll: () => enlaces, dispatchEvent() {} },
      CustomEvent: class {},
    });
    vm.runInContext(source, context);
    await context.cargarUsuarioNav();
    assert.deepEqual(enlaces.filter(a => !a.hidden).map(a => a.dataset.nav), esperados, rol);
  }
  console.log('Navegacion por rol: OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
