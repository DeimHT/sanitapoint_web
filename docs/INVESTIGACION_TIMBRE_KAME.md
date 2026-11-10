# Investigación del timbre KAME — 10 de noviembre de 2026

## Conclusión

La integración utiliza la ruta publicada para recuperar el XML firmado. Se confirmó un defecto local de diagnóstico: cualquier error lógico recibido con HTTP 200 se convertía en «KAME todavía no tiene disponible el documento»; al agotar los intentos también se descartaba la causa original. Por ello, los dos avisos reportados no permiten concluir que KAME simplemente esté demorando.

No se ha determinado la causa de las cuatro boletas del incidente. La base y los registros de ese servidor están en otro equipo, accesible por AnyDesk. La copia local y sus credenciales no prueban el comportamiento de producción.

## Contrato comprobado en la documentación de KAME

1. [Registrar boleta](https://mzujlb48px.apidog.io/registro-de-venta-boleta-34273186e0): `POST /api/Documento/addVenta`, respuesta con `Estado`, `Folio`, `Id` y `Error`. Conservar folio e identificador; no confundirlos.
2. [Recuperar XML](https://mzujlb48px.apidog.io/obtener-xml-registro-de-ventas-38233649e0): `GET /api/Documento/getDocumentoXML/{rutEmisor}/{tipoDocumento}/{folio}`, autenticación Bearer. Para boleta afecta, tipo `39`; RUT de la empresa emisora, sin puntos y con guion. El campo `Xml` contiene el DTE firmado, TED y firma digital.
3. [Recuperar PDF](https://mzujlb48px.apidog.io/obtener-pdf-registro-de-ventas-38139918e0): misma identidad, ruta `getDocumentoPDF`; contenido en `ArchivoBase64PDF`.
4. [Consultar registro de venta](https://mzujlb48px.apidog.io/obtener-registro-en-ventas-35654367e0): `GET /api/Documento/getVenta/{documento}/{numero}`; nombre `Boleta Electrónica`, número igual al folio. Sirve para distinguir existencia en ventas de disponibilidad del documento electrónico.
5. [Control de tráfico](https://mzujlb48px.apidog.io/informaci%C3%B3n-general-8702595f0): máximo de 180 peticiones por minuto por IP y bloqueo temporal con HTTP 403. No hay evidencia de que cuatro ventas, por sí solas, alcancen ese límite; cuenta también el tráfico de otras integraciones que compartan IP.

No se encontró una opción documentada para forzar disponibilidad inmediata del XML ni un plazo garantizado de publicación. Esto es un límite de lo publicado, no una prueba de una falla general del proveedor. Repetir la emisión para conseguir el timbre puede duplicar el documento y no es una recuperación válida.

## Evidencia obtenida en esta copia local

- Siete ventas están marcadas `ok`, con folios 5007278–5007284 y XML con TED en cache. Sus fechas de emisión son del 16 y 19 de octubre. Esto demuestra que hay documentos guardados; no verifica criptográficamente sus firmas ni su aceptación ante el SII.
- La configuración local está en modo `mock`, con credenciales OAuth configuradas. No se cambió `.env` ni se emitió ninguna boleta durante la investigación.
- Se consultó el folio existente 5007284 mediante GET, usando las credenciales locales y el RUT guardado, que coincide con el configurado.
- Tanto XML como PDF respondieron HTTP 200 con `Estado: "Error"` y `ErrorMessage: "Documento : No existe el documento electronico registrado en el ERP"`.
- `getVenta/Boleta Electrónica/5007284` respondió que no encontró ese registro. Por tanto, para esa consulta no se trata de esperar unos segundos por un timbre nuevo. Aún hay que comprobar la correspondencia entre credenciales, empresa, ambiente y documento; no se atribuye esta respuesta al servidor del incidente.
- No se consultaron folios adivinados de la fotografía ni se escribieron cambios en ventas o en los documentos guardados.

## Corrección aplicada

- Conservar el motivo de `ErrorMessage` y el código HTTP en el aviso y en consola. Ocultar credenciales, correos y RUT en los detalles de error recibidos.
- Mantener el último motivo cuando se agota la espera.
- Reintentar de forma limitada los errores de disponibilidad; detener los demás rechazos para revisión.
- Identificar HTTP 403 como acceso rechazado, con indicación de permisos o límite de tráfico, sin insistir durante la atención.
- Respetar `Retry-After` cuando el proveedor lo envía; no consultar antes del plazo si este excede la espera de la atención.
- Mantener la venta emitida y su folio durante cualquier fallo de recuperación; ninguna recuperación llama a `addVenta`.
- Incluir `scripts/diagnosticar_kame.py` para consultar las últimas boletas directamente en el servidor sin modificar la base, cache ni configuración. Ver el comando en [KAME.md](KAME.md#diagnosticar-un-timbre-no-disponible).

## Comprobación pendiente en el servidor

Ejecutar el diagnóstico para las cuatro boletas afectadas, o para un ticket concreto si ya hay ventas posteriores, y revisar el informe. No hace falta configurar Visual Studio remoto ni copiar toda la base de datos. Si KAME encuentra el registro comercial pero no entrega XML/PDF para la identidad correcta, el informe permitirá pedir a su soporte que revise ese folio. Si tampoco encuentra el registro comercial, primero hay que comprobar empresa, ambiente, credenciales y folio.

Los cambios están preparados en el repositorio local. No se ha actualizado el servidor remoto.

## Validación realizada

Pasaron 47 pruebas de documentos y cliente KAME con respuestas simuladas, incluyendo errores HTTP 200, recuperación posterior sin reemisión, rechazos de permisos, `Retry-After` numérico y por fecha, ocultación de credenciales, consulta de XML/PDF/registro ERP y lectura SQLite sin crear ni modificar la base. Se ejecutó también el comando real sobre el ticket local T000008: produjo el diagnóstico esperado y los hashes de la base SQLite y `.env` permanecieron iguales. `git diff --check` no detectó errores de formato.
