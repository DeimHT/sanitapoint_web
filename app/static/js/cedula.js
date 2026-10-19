// Parse only the text supplied by the reader; never visit the QR URL.
function leerCedula(texto) {
  if (!texto || texto.length > 8192) throw new Error("La lectura está vacía o es demasiado larga.");
  let campos = {};
  try {
    const url = new URL(texto.trim());
    if (!["http:", "https:"].includes(url.protocol)) throw new Error();
    url.searchParams.forEach((v, k) => campos[k.toLowerCase()] = v);
  } catch (_) {
    if (texto.trim().startsWith("{")) {
      try { Object.entries(JSON.parse(texto)).forEach(([k, v]) => campos[k.toLowerCase()] = v); }
      catch (_) { throw new Error("El contenido del QR no se pudo interpretar."); }
    }
  }
  let rut = String(campos.run || campos.rut || "").replace(/\./g, "").replace(/\s/g, "").toUpperCase();
  if (!rut && /^\d{6,8}-[0-9k]$/i.test(texto.trim())) rut = texto.trim().toUpperCase();
  // Lector con distribucion de teclado distinta a la de Windows: los simbolos de la URL
  // llegan cambiados (RUN=20622632-3 -> RUN¿20622632'3) pero los digitos no. El digito
  // verificador se sigue validando abajo.
  const deformado = !rut && texto.match(/RUN.(\d{6,8}).([0-9K])(?![0-9K])/i);
  if (deformado) rut = `${deformado[1]}-${deformado[2].toUpperCase()}`;
  if (!/^\d{6,8}-[0-9K]$/.test(rut)) throw new Error("Este QR no contiene un RUN/RUT legible. Ingresa los datos manualmente.");
  const [numero, dv] = rut.split("-");
  let suma = 0, factor = 2;
  for (const digit of numero.split("").reverse()) { suma += Number(digit) * factor; factor = factor === 7 ? 2 : factor + 1; }
  const calculado = 11 - suma % 11;
  const esperado = calculado === 11 ? "0" : calculado === 10 ? "K" : String(calculado);
  if (dv !== esperado) throw new Error("El RUT leído no tiene un dígito verificador válido. Revisa la lectura.");
  const nombre = String(campos.name || campos.nombre || "").trim().slice(0, 200);
  return { rut, nombre };
}
if (typeof module !== "undefined") module.exports = { leerCedula };
