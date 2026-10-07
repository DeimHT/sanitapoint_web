function renderCuadre(c) {
  const numero = (v) => v == null ? "—" : Number(v).toLocaleString("es-CL");
  const dinero = (v) => v == null ? "—" : fmtMonto(v);
  const fila = (label, value) => `<tr><th>${label}</th><td>${value}</td></tr>`;
  const torniquete = (tipo, label) => `<tr><th>${label}</th>` +
    `<td>${numero(c[`torniquete_${tipo}_inicial`])}</td>` +
    `<td>${numero(c[`torniquete_${tipo}_final`])}</td>` +
    `<td>${numero(c[`personas_${tipo}`])}</td>` +
    `<td>${numero(c[`ventas_${tipo}`])}</td>` +
    `<td>${tipo === "bano" ? numero(c.pases_bano) : "0"}</td>` +
    `<td>${numero(c[`contador_${tipo}`])}</td>` +
    `<td>${numero(c[`diferencia_${tipo}`])}</td></tr>`;
  return `<h3>Cuadre de dinero</h3><table><tbody>` +
    fila("Caja Inicial", dinero(c.saldo_inicial)) +
    fila("Ventas en efectivo (+)", dinero(c.ventas_efectivo)) +
    fila("Retiros (−)", dinero(c.total_retiros)) +
    fila("Efectivo esperado", dinero(c.saldo_esperado)) +
    fila("Caja Final", dinero(c.saldo_final)) +
    fila("Cambio de dinero (final − inicial)", dinero(c.cambio_dinero)) +
    fila("Ingreso ajustado por retiros (final − inicial + retiros)", dinero(c.ingreso_ajustado_retiros)) +
    fila("Diferencia de dinero (final − esperado)", dinero(c.diferencia_dinero)) +
    `</tbody></table><p>Una diferencia negativa indica faltante; positiva, sobrante. Los pagos electrónicos no se suman al efectivo.</p>` +
    `<h3>Cuadre de torniquetes</h3><div style="overflow-x:auto"><table><thead><tr>` +
    `<th>Servicio</th><th>Inicial</th><th>Final</th><th>Personas</th><th>Ventas</th><th>Pases gratuitos</th><th>Contador interno</th><th>Diferencia</th>` +
    `</tr></thead><tbody>${torniquete("bano", "Baño")}${c.servicio === "Ba\u00f1o 2" ? "" : torniquete("ducha", "Ducha")}</tbody></table></div>` +
    `<p>Personas = final − inicial. Diferencia = personas − contador interno. Un valor positivo indica más pasos que accesos registrados. “—” indica que aún no hay lectura o que falta en un turno antiguo.</p>`;
}
