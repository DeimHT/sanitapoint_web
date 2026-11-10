(() => {
  const imagen = document.getElementById("ticket");
  let solicitada = false;
  function informar(evento) {
    return fetch(imagen.dataset.eventos + evento, {
      method: "POST", credentials: "same-origin", keepalive: true,
    }).then(res => {
      if (!res.ok) console.error("No se pudo registrar el evento de impresión", res.status);
    }).catch(error => console.error("No se pudo registrar el evento de impresión", error));
  }
  window.addEventListener("afterprint", () => {
    if (solicitada) informar("dialogo_cerrado");
  });
  function imprimir() {
    if (solicitada) return;
    if (!imagen.naturalWidth) { informar("error"); return; }
    solicitada = true;
    informar("solicitada");
    try { window.focus(); window.print(); }
    catch { informar("error"); }
  }
  imagen.addEventListener("load", imprimir, { once: true });
  imagen.addEventListener("error", () => informar("error"), { once: true });
  if (imagen.complete) imprimir();
})();
