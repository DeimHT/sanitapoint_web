# Documentos con timbre de KAME

La integracion se basa en la documentacion API Siigo Kame Chile compartida para este proyecto. No necesita acceso a una boleta ya emitida para ejecutar las pruebas simuladas.

## Contrato utilizado

- [Autenticacion](https://mzujlb48px.apidog.io/api-auth0-34066797e0): OAuth client credentials, token Bearer.
- [Registro de boleta](https://mzujlb48px.apidog.io/registro-de-venta-boleta-34273186e0): `POST /api/Documento/addVenta`. Se conservan `Folio` e `Id`.
- [XML firmado](https://mzujlb48px.apidog.io/obtener-xml-registro-de-ventas-38233649e0): `GET /api/Documento/getDocumentoXML/{rutEmisor}/{tipoDocumento}/{folio}`. Se lee `Xml` de la respuesta, que contiene el TED y la firma. El RUT corresponde a la empresa emisora, sin puntos y con guion; para la boleta afecta usamos `39`.
- [PDF oficial](https://mzujlb48px.apidog.io/obtener-pdf-registro-de-ventas-38139918e0): `GET /api/Documento/getDocumentoPDF/{rutEmisor}/{tipoDocumento}/{folio}`. Se decodifica `ArchivoBase64PDF`. El ejemplo publicado es un texto con esa etiqueta; tambien se admite el objeto JSON con ese campo. El PDF se entrega sin reconstruir ni modificar sus paginas.

Las consultas de documentos existentes nunca llaman a `addVenta`. No se presupone una URL de descarga en la respuesta de emision ni se usa el identificador interno como folio.

## Configuracion del servidor

El punto de venta completa `Direccion` y `Ciudad` con los campos Dirección y Ciudad guardados en **Configuración > Datos de la empresa** (`empresa_direccion` y `empresa_ciudad`). No se requiere duplicarlos en `.env`. Si no hay dirección guardada, se envia `Sin dirección` para evitar el rechazo por texto vacio.

En `.env` configura las credenciales existentes y `KAME_RUT`, con el RUT de la empresa emisora. Los documentos nuevos guardan RUT y tipo junto a la venta para conservar su identidad aunque cambie la configuracion. Para documentos anteriores sin ese dato se utiliza el RUT configurado al recuperarlos.

Cuando el XML individual no contiene la caratula con la resolucion, configura los datos reales del emisor:

```dotenv
KAME_RESOLUCION_NUMERO=NUMERO_REAL_DEL_EMISOR
KAME_RESOLUCION_FECHA=AAAA-MM-DD
```

No copies la resolucion de los ejemplos. La impresion termica solicita estos datos si faltan; el PDF oficial se puede recuperar independientemente. Los cambios `KAME_*` de `.env` se leen en la siguiente operacion, sin reiniciar; las variables del sistema tienen prioridad. Instala las dependencias actualizadas de `requirements.txt` y reinicia si estas cambian.

## Venta, impresion y recuperacion

Despues de que KAME confirma la emision, se intenta recuperar el XML con el mismo cliente y token. La venta permanece emitida aunque falle esa consulta. Durante el cobro y al usar Imprimir se reintenta automaticamente la consulta del XML. Si el timbre sigue pendiente al agotarse la espera, se permite atender otra venta y recuperarlo desde Historial > Imprimir. Cada recuperacion admite hasta seis consultas de lectura, con pausas de 1, 2, 3, 5 y 5 segundos y un presupuesto de espera de 20 segundos. Se respeta un `Retry-After` mayor; si excede la espera disponible, se termina sin consultar antes de ese plazo. Solo se reintentan consultas de documentos existentes; nunca se repite la emision para conseguir su timbre.

Las solicitudes POST del navegador tienen un limite de espera de 60 segundos. Si vence durante el cobro, se muestra un aviso de resultado incierto y no se permite repetirlo desde esa pantalla: hay que comprobar Historial y el estado de KAME antes de continuar. Cancelar la espera del navegador no cancela la operacion en el servidor. La consola registra el inicio y la duracion del envio, el folio confirmado y los errores HTTP o de conexion al consultar documentos, sin imprimir credenciales.

Para el ticket termico se conserva el texto original del TED, incluidos sus caracteres ISO-8859-1 y saltos de linea. Se cotejan RUT emisor, tipo, folio, fecha, receptor y monto con el documento y la venta. Se rechazan XML con DTD, entidades o datos que no coincidan. Esta comprobacion de correspondencia no es una verificacion criptografica independiente de la firma ni una consulta de aceptacion ante el SII.

El PDF417 utiliza compactacion binaria, correccion nivel 5 y modulos enteros. El ticket de 80 mm muestra la informacion tributaria recibida, el timbre y los datos de resolucion. La consulta **Ver PDF** recupera el documento oficial de KAME, cuyo formato de pagina lo determina KAME. Si el timbre no cabe en el formato termico, se indica usar ese PDF sin reducir el codigo hasta hacerlo ilegible. Referencias de representacion: [instructivo PDF417 del SII](https://www.sii.cl/factura_electronica/factura_mercado/instructivo_emision.pdf) y [dimensiones para boletas](https://www.sii.cl/preguntas_frecuentes/bol_electr_vtas_serv/001_380_6277.htm).

Si esta activada la impresion automatica de **Este computador**, se abre el dialogo del navegador cuando el timbre esta listo. Si la boleta ya fue emitida pero falta el timbre, se muestra **Boleta emitida; timbre pendiente** y se permite seguir atendiendo. El folio se conserva; desde **Historial > Imprimir** se puede recuperar el documento de esa misma venta. Solo una emision con estado pendiente de confirmacion bloquea nuevos cobros en esa caja, incluso desde otra pestana. **Imprimir boleta** reintenta recuperar el documento existente, sin volver a cobrar ni emitir. No se sustituye silenciosamente una boleta real por un comprobante sin timbre. Los pases libres siguen sin documento tributario ni impresion.

XML y PDF se guardan bajo `data/documentos_kame`, fuera de los archivos publicos. Se verifican permisos de la venta antes de acceder a ellos. El cache evita consultas repetidas y permite reimprimir documentos ya recuperados sin internet. Los errores no se guardan como documentos validos. Respalda esta carpeta aparte si necesitas conservar las copias locales para operar sin conexion despues de restaurar: el respaldo diario SQLite incluye los registros, pero no esos archivos.

La documentacion general de KAME establece un limite de **180 peticiones por minuto por IP** y un bloqueo temporal con **HTTP 403** al superarlo. El cache, las pausas entre consultas y el limite de intentos reducen peticiones. Un 403 tambien puede corresponder a permisos; no se reintenta automaticamente durante la atencion. [Politica de trafico](https://mzujlb48px.apidog.io/informaci%C3%B3n-general-8702595f0).

## Diagnosticar un timbre no disponible

KAME puede responder **HTTP 200** con `Estado: "Error"` y una lista `Error` con `ErrorMessage`. El HTTP 200 no confirma que exista el documento. Se conserva ese motivo en pantalla, en `kame_error_documento` y en consola con ticket y folio, ocultando credenciales y datos personales. Si se agotan los reintentos, el aviso conserva el ultimo motivo; no se reemplaza por una supuesta demora generica. La ausencia del documento admite una espera limitada porque puede ocurrir justo despues de emitir; no prueba que vaya a aparecer. Los otros rechazos del JSON requieren revision y no se reintentan a ciegas.

Para revisar el servidor mediante AnyDesk, abre PowerShell **en la carpeta de la aplicacion** y ejecuta:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\diagnosticar_kame.py --ultimas 4 > diagnostico-kame.txt
```

Tambien admite `--ticket T000123` y `--base-datos C:\ruta\sanitapoint.db`. Usa la base SQLite configurada en `DATABASE_URL` o, por defecto, `data/sanitapoint.db`; la abre con `mode=ro`. No modifica ventas, documentos en cache ni `.env`, ni llama a `addVenta`. Usa las credenciales existentes para consultar documentos ya registrados, incluso si la configuracion local esta en modo mock. Realiza consultas nuevas para comparar la disponibilidad remota con el cache local. El informe contiene ticket, folio, estado local, disponibilidad del XML/PDF y existencia en el ERP; no incluye RUT, credenciales ni el contenido de los documentos. Los mensajes de consulta se muestran por separado en consola.

La consulta adicional [Obtener Registro en Ventas](https://mzujlb48px.apidog.io/obtener-registro-en-ventas-35654367e0) usa `GET /api/Documento/getVenta/{documento}/{numero}`, con `Boleta Electrónica` y el folio. Permite distinguir el registro comercial del XML/PDF electronico:

- Registro ERP presente y XML/PDF ausentes: verificar RUT emisor/tipo y pedir a KAME revisar la generacion electronica de ese folio. No basta con aumentar la espera.
- Registro ERP tambien ausente: verificar que folio, empresa, ambiente y credenciales correspondan al servidor que emitio. No atribuirlo automaticamente a una caida de KAME.
- XML recibido pero rechazado localmente: revisar identidad, monto, receptor, TED, resolucion o dependencias segun el motivo registrado.

El analisis del incidente y sus limites estan en [Investigacion del timbre](INVESTIGACION_TIMBRE_KAME.md).

## Validacion

Las pruebas automatizadas usan respuestas simuladas y firmas sinteticas que no tienen validez tributaria. Cubren autenticacion, rutas documentadas, Base64, integridad de transporte, identidad, cache, recuperacion, errores y acceso por cajero. Tambien se comprobo con un lector independiente que el PDF417 generado recupera exactamente los bytes del TED sintetico, tanto aislado como dentro del ticket completo.

No se emitieron boletas reales ni se utilizaron credenciales de produccion en estas pruebas. Queda pendiente comprobar el flujo con una emision autorizada en KAME y escanear el papel de la impresora instalada, usando 80 mm, sin margenes ni encabezados y sin reducir la escala.

### Emision durante la atencion

Antes del primer cobro en modo real son obligatorios las credenciales, KAME_USER, KAME_RUT y los datos KAME_RESOLUCION_NUMERO y KAME_RESOLUCION_FECHA. La configuracion incompleta rechaza la operacion sin registrar otra venta. Activa la impresion automatica en **Este computador** para abrir la impresion al recibir el timbre.

La API publicada no documenta una opcion para forzar la disponibilidad inmediata del XML ni permite garantizar que KAME responda durante una interrupcion. El sistema espera y recupera el documento de la misma emision; no genera un timbre local inventado ni presenta una boleta sin timbre como terminada. Si la emision quedo en curso por un reinicio o hay una respuesta de emision ambigua, hay que comprobar el documento en KAME antes de cualquier nueva emision. No existe reemision automatica ante un timeout.
