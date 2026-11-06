# SanitaPoint Web

SanitaPoint ayuda a llevar el cobro de **baños y duchas**: registra las ventas, entrega tickets y permite revisar el dinero y los accesos de cada turno. También se conecta con KAME para emitir boletas electrónicas.

Se usa desde el navegador. Un computador principal mantiene el sistema funcionando y los equipos de caja se conectan a él por la misma red del local.

## Cómo entrar

1. En el computador principal, abre la carpeta de SanitaPoint y haz doble clic en **`iniciar_servidor.bat`**.
2. Espera a que termine de iniciar. **Deja esa ventana abierta mientras se esté usando el sistema.**
3. En ese computador, abre [SanitaPoint](http://localhost:8000). Si la página todavía no carga, espera unos segundos y vuelve a intentarlo.
4. En los otros equipos, abre en el navegador la dirección que aparece en la ventana de inicio. Será parecida a `http://192.168.1.10:8000`; usa la que muestre tu equipo.
5. Ingresa con tu usuario y contraseña.

Puedes guardar la dirección en los favoritos del navegador para encontrarla más rápido.

### Aplicar cambios mientras funciona

Los archivos de inicio activan la recarga automática: al guardar código Python dentro de `app/`, el servidor espera las solicitudes en curso y recarga el proceso. Puede haber una pausa breve; no hace falta cerrar la ventana. Para activar esta función en un servidor que ya estaba abierto, reinícialo una sola vez con el archivo de inicio actualizado.

Los cambios guardados en **Configuración** y las variables `KAME_*` de `.env` se aplican en la siguiente operación, sin recargar el proceso. Las variables del sistema tienen prioridad sobre `.env`. Los cambios HTML, CSS y JavaScript se ven al refrescar el navegador. Cambiar la base de datos, el puerto, instalar dependencias o actualizar los archivos de inicio sigue requiriendo reiniciar. En el arranque por tareas (`scripts/servidor_local.py`), usa `--no-reload` si necesitas desactivar la recarga automática.

### Si es la primera vez

La persona encargada de instalar el sistema debe tener **Python 3.11 o superior** en el computador principal, con la opción **“Add Python to PATH”** marcada durante su instalación. Al abrir SanitaPoint por primera vez, se descargan los componentes necesarios; hace falta internet y puede tardar unos minutos.

En una instalación nueva, la cuenta inicial es:

| Usuario | Contraseña |
|---|---|
| `admin` | `admin123` |

**Cambia esa contraseña al entrar:** ve a **Cuentas**, edita la cuenta `admin` y escribe una nueva contraseña. Crea una cuenta para cada persona que vaya a trabajar con el sistema.

Antes de comenzar a vender, pide al administrador que revise los precios, los datos del negocio, la impresora y la conexión con KAME. Para emitir boletas reales, el acceso a KAME debe estar configurado y el computador principal debe tener internet.

En Mac, el archivo de inicio es **`iniciar_servidor.command`**. Si no abre, solicita ayuda a quien instaló el sistema.

## El trabajo de cada día

### 1. Abrir tu caja

Entra con tu propia cuenta y ve a **Caja → Abrir caja**. Completa:

- **Caja Inicial:** el dinero en efectivo con el que comienzas.
- **Torniquete Baño Inicial:** el número que marca el contador del torniquete de baño.
- **Torniquete Ducha Inicial:** el número que marca el contador del torniquete de ducha.

Pulsa **Abrir**. Cada cajero trabaja con su propio turno; necesitas tener la caja abierta para registrar ventas.

### 2. Registrar una venta

1. Entra a **Venta**.
2. Elige la forma de pago: **Efectivo** o **Tarjetas**.
3. Revisa el precio y pulsa el servicio: **Uso de Baño** o **Ducha**. **Al pulsarlo se registra la venta.**
4. Revisa el resultado en pantalla: allí se indica el ticket, el estado de la boleta y si se envió a la impresora.

Puedes abrir el comprobante con **Ver PDF**. En **Historial** puedes consultar las ventas y volver a obtener sus tickets.

Si aparece un error de KAME, **la venta puede haber quedado registrada aunque la boleta no se haya emitido**. Revisa el Historial y avisa al encargado para que compruebe el estado en KAME antes de repetir la operación.

Si el resultado dice **“modo prueba”**, corresponde a una boleta de prueba. Pide al administrador que revise la configuración antes de usar el sistema para ventas reales.

### 3. Registrar un pase libre

Los pases libres permiten registrar un acceso gratuito al **baño** para una persona registrada en **Clientes**.

1. En **Venta**, pulsa **Registrar PASE LIBRE**.
2. Busca a la persona por su nombre o RUT y pulsa **Elegir**.
3. Si se ofrecen varios servicios de baño, selecciona el que corresponda.
4. Comprueba que aparezca el aviso de pase registrado.

El sistema controla el máximo de pases diarios por persona y avisa cuando se alcanza el límite. El administrador puede ajustar ese límite en **Config**.

### 4. Registrar un retiro de dinero

Cuando se saca dinero de una caja durante el turno, el **supervisor o administrador** debe registrarlo en **Caja → Retiro**: selecciona la caja del usuario, indica el monto y el motivo, y pulsa **Retirar**.

Así, ese dinero se tiene en cuenta al revisar el cierre.

### 5. Cerrar tu turno

1. Cuenta el efectivo que queda en tu caja.
2. Ve a **Caja → Cerrar caja**.
3. En **Caja Final**, escribe el efectivo contado.
4. Ingresa las lecturas finales de los torniquetes de baño y ducha.
5. Pulsa **Cerrar** y revisa el resumen.

El sistema compara el efectivo contado con lo que debería haber: dinero inicial, más ventas en efectivo, menos retiros. Las transferencias no se suman al efectivo de la caja.

También compara los accesos registrados con el avance de los torniquetes. Si hay un faltante, sobrante o diferencia de accesos, revísalo con el encargado; la diferencia queda registrada.

Al terminar, pulsa **Salir** para cerrar tu sesión. Salir de la cuenta no reemplaza el cierre de caja.

Después de cerrar, pulsa **Imprimir cierre** en el resumen del último cierre de **Caja**. Contabilidad y Administración también pueden reimprimir desde **Cierres**, junto a **Ver cuadre**. El comprobante incluye totales del turno, efectivo esperado y contado, retiros, diferencias y lecturas de torniquetes. Usa la misma impresora térmica de las boletas: selecciona papel de **80 mm**, escala **100 %**, sin encabezados ni pies del navegador. Imprimir o cancelar el diálogo no modifica el cierre guardado.

## Qué puede hacer cada persona

El menú muestra las opciones disponibles para tu cuenta.

| Tipo de cuenta | Funciones principales |
|---|---|
| **Cajero** | Abrir y cerrar su caja, registrar ventas y pases libres, consultar su propio historial y gestionar clientes. |
| **Supervisor** | Registrar retiros y consultar el historial completo con su cajero y servicio. |
| **Contabilidad** | Consultar historial, reportes y cierres; administrar cuentas y contraseñas. |
| **Administrador** | Acceder a todas las funciones y ajustar precios, impresora y configuración. |

**Clientes** contiene las personas que usan los servicios y sus pases. **Cuentas** contiene las personas que ingresan a trabajar al sistema. Solo un administrador puede crear o modificar cuentas administradoras.

Si olvidaste tu contraseña, pide a Contabilidad o al administrador que la cambie desde **Cuentas**. Para una cuenta administradora, debe hacerlo otro administrador.

## Consultar ventas y cierres

- **Historial:** busca ventas anteriores y consulta sus tickets.
- **Cierres:** revisa los turnos y pulsa **Ver cuadre** para ver el detalle del dinero y los accesos.
- **Reportes:** elige un día, un rango de fechas o un servicio y descarga el informe en **PDF** o **Excel**. También puedes obtener un reporte anual.

## Guardar una copia de los datos

Los datos se guardan en el computador principal, dentro de la carpeta **`data`** de SanitaPoint. Guarda una copia al finalizar la jornada:

1. Comprueba que todas las cajas hayan terminado y que nadie esté usando el sistema.
2. Detén SanitaPoint cerrando la ventana de inicio del computador principal.
3. Copia la carpeta completa **`data`** a un pendrive o a otro lugar de respaldo. Ponle la fecha para identificarla.
4. Vuelve a iniciar SanitaPoint si necesitas seguir trabajando.

Esta copia incluye los registros, los tickets guardados y otros archivos necesarios para el funcionamiento. **No borres ni cambies los archivos de la carpeta original.** Si necesitas recuperar una copia, pide ayuda al encargado antes de reemplazar los datos actuales.

## Si algo no funciona

| Problema | Qué hacer |
|---|---|
| No abre la página | Comprueba que el computador principal esté encendido, que la ventana de SanitaPoint siga abierta y que ambos equipos estén conectados a la misma red. Usa la dirección indicada al iniciar. |
| Aparece “No se encontró Python” | Pide al encargado que revise la instalación de Python en el computador principal. |
| No puedes registrar una venta | Revisa que hayas abierto tu caja con la cuenta que estás usando. |
| El ticket no sale en papel | Revisa que la impresora esté encendida, conectada y con papel. Abre el PDF de la venta y pide al administrador que revise la impresora en **Este computador**. No registres otra venta solo para imprimir. |
| Aparece un error de KAME | Revisa el Historial y avisa al encargado. Antes de repetir la venta, hay que comprobar si KAME recibió la boleta. |
| No aparece una opción del menú | Puede que tu cuenta no tenga permiso para usarla. Consulta al administrador. |

Para instalación manual y detalles técnicos, la persona encargada puede consultar la [guía técnica](GUIA.md).


## Configurar la impresora ONE R200

Instala la impresora con su controlador en cada computador de caja. En **Este computador**, elige si abrir la impresion al vender o usar el boton **Imprimir boleta**. Al imprimir, selecciona la impresora local en el dialogo del navegador, papel de 80 mm, sin margenes ni encabezados. Comprueba una boleta fisica en cada puesto antes de comenzar a operar.

El sistema usa el navegador del puesto para imprimir; no envia trabajos a los dispositivos del servidor. La opcion automatica abre el dialogo: requiere confirmacion y no garantiza que salga papel. Puedes volver a imprimir una venta sin cobrar ni emitir nuevamente en KAME.

### Importar cuentas de acceso desde Excel

En **Cuentas → Importar Excel**, descarga la plantilla y completa la hoja **Cuentas** con las columnas `usuario`, `nombre`, `rol`, `contrasena`. Los roles permitidos son `cajero`, `supervisor`, `contabilidad` y `administrador`; solo un administrador puede crear cuentas administradoras. Se admiten hasta 500 cuentas y archivos de hasta 1 MB.

Pulsa **Revisar archivo** para ver las cuentas antes de crearlas. Las contraseñas no se muestran. Si hay errores, corrige las filas indicadas y vuelve a cargar el archivo; no se crea ninguna cuenta hasta que todas sean válidas. Luego pulsa **Crear cuentas**. Las cuentas existentes no se modifican y las nuevas contraseñas se almacenan mediante hash.

### Personas con pase libre y lector USB

En **Pases libres** puedes **Ingresar datos** manualmente o **Escanear cédula**. Usa una pistola que lea QR en modo USB teclado (HID), con Enter al terminar. La lectura se recibe en el campo enfocado del equipo donde está abierto el navegador. Puedes pegar el contenido para probar sin hardware. Se reconocen RUN/RUT y nombre cuando vienen como parámetros de la URL o campos JSON; si no vienen, completa los datos manualmente. No se abre el enlace ni se consulta Registro Civil.

En **Este computador**, activa o desactiva el lector y prueba una lectura. Los ajustes de lector e impresion se guardan en el navegador de ese equipo y permanecen al cambiar de cajero. Usa siempre el mismo perfil del navegador y la misma direccion del servidor; borrar los datos del sitio o usar modo privado pierde estos ajustes. Cada pistola se conecta al computador donde se usa. Revisa los datos antes de guardar; una lectura no otorga un pase automaticamente.

### Operacion de los dos banos

Solo puede existir una caja abierta por servicio: si Pepe abre en Bano 1, Juan debe esperar a que Pepe cierre. Bano 2 puede operar al mismo tiempo. La restriccion tambien protege intentos simultaneos. Un cajero con turno abierto debe volver a su servicio antes de continuar o cerrar; salir de la sesion no cierra la caja.

El cajero ve solo las ventas de su cuenta, incluidos sus turnos anteriores. Tampoco puede acceder al PDF ni imprimir tickets ajenos por URL. Supervisor, Contabilidad y Administrador ven el historial completo con cajero y bano. Las tarifas, datos de empresa, pie del ticket, limites de pases y KAME son compartidos.

Antes de actualizar, cierra los turnos de la version anterior y respalda la base. Al reiniciar se agrega la restriccion a bases existentes. Si ya hay dos turnos abiertos en un mismo servicio, el inicio informa el conflicto: deben conciliarse primero; el sistema no los cierra automaticamente ni reasigna ventas historicas.

Al ingresar con Baño 2, los turnos nuevos no solicitan lecturas de ducha ni permiten vender ese servicio. Baño 1 mantiene las lecturas de baño y ducha. El servicio queda guardado en la caja durante todo el turno.


### Actualizaciones desde GitHub privado

La [seccion 5.7 de la guia](GUIA.md#57-actualizar-desde-un-repositorio-privado-de-github-sin-cuenta-personal-en-el-servidor) explica como usar una clave de despliegue de solo lectura, sin iniciar una cuenta personal en el servidor. Incluye una tarea que consulta main cada cinco minutos, espera a que cierren las cajas y respalda antes de actualizar, con recuperacion ante fallo de arranque. La clave y las tareas se configuran una vez en el servidor del terminal.


### Boletas con timbre KAME

La impresion termica recupera el XML firmado y representa su TED original como PDF417. **Ver PDF** entrega el PDF oficial. Configura el RUT emisor y los datos de resolucion en `.env` segun [la guia de integracion KAME](docs/KAME.md). Si el documento esta pendiente, reintenta desde Imprimir sin registrar una nueva venta. Las pruebas actuales son simuladas; falta validar una emision autorizada y el papel de la impresora del terminal.
