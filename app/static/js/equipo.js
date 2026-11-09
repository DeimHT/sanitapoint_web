const equipoLocal = {
  leer() {
    try { return { lector_modo: "teclado", ...JSON.parse(localStorage.getItem("sanitapoint.equipo") || "{}"), impresora_automatica: "1" }; }
    catch { return { impresora_automatica: "1", lector_modo: "teclado" }; }
  },
  guardar(valores) { localStorage.setItem("sanitapoint.equipo", JSON.stringify(valores)); },
  lector() { return { modo: this.leer().lector_modo }; },
  async imprimir(ticket) {
    // Verifica permisos antes de abrir el documento en el puesto actual.
    await api.post(`/api/ventas/${encodeURIComponent(ticket)}/imprimir`, {});
    const anterior = document.getElementById("impresion_local");
    if (anterior) anterior.remove();
    const marco = document.createElement("iframe");
    marco.id = "impresion_local";
    marco.title = "Impresion del ticket";
    marco.style.cssText = "position:fixed;left:-10000px;width:320px;height:600px;border:0";
    marco.src = `/api/ventas/${encodeURIComponent(ticket)}/imprimir`;
    document.body.appendChild(marco);
    return { ok: true, mensaje: "" };
  }
};
