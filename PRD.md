# PRD — GOTES: Control histórico de traspasos

**Versión:** 2.0  
**Estado:** V1 implementada  
**Tipo:** Aplicación web interna multiempresa  
**Stack:** Django, templates, Tailwind CSS, Alpine.js y SQLite  
**Zona horaria:** `America/La_Paz`

## 1. Visión

GOTES registra evidencia independiente de los movimientos físicos de productos entre sucursales. Permite reconstruir qué se envió, quién lo preparó y despachó, qué recibió el destino, qué diferencias existieron y cuándo el movimiento fue registrado en el sistema comercial principal.

GOTES no es un inventario, POS o ERP. Sus cantidades son informativas y ninguna acción modifica existencias, ventas o contabilidad.

Principio central:

> El sistema registra lo que ocurrió; no reescribe el pasado para hacer coincidir los números.

## 2. Alcance V1

La V1 incluye:

- autenticación con usuario y contraseña;
- empresas y sucursales;
- usuarios, roles y permisos operativos;
- catálogo empresarial de productos;
- creación, preparación y despacho de traspasos;
- evidencias protegidas de salida y recepción;
- recepción en borrador y confirmación final;
- diferencias, productos inesperados y productos dañados;
- incidencias agrupadas y resolución;
- cierre y anulación controlados;
- conciliación manual con el sistema comercial;
- notificaciones internas;
- dashboard por perfil;
- búsqueda, filtros y exportación CSV;
- línea temporal y auditoría;
- panel empresarial propio;
- Django Admin exclusivo para superusuarios;
- funcionamiento responsive en móvil y escritorio.

Quedan fuera:

- inventario y actualización de stock;
- precios, ventas, compras, clientes y proveedores;
- transporte, vehículos o conductores;
- autorregistro público;
- integraciones automáticas con sistemas comerciales;
- personalización visual por empresa;
- API REST;
- correo, WhatsApp, Web Push o PWA;
- despliegue productivo y PostgreSQL.

## 3. Multiempresa y aislamiento

Una instalación contiene varias empresas. Todo registro operativo pertenece a una empresa y ninguna cuenta empresarial puede descubrir o acceder a información de otra.

El aislamiento cubre:

- URLs y UUID;
- consultas y búsquedas;
- catálogos;
- dashboard y reportes;
- exportaciones CSV;
- notificaciones;
- auditoría;
- archivos y evidencias;
- administración empresarial.

Los correlativos visibles se reinician por empresa y año. Por ello dos empresas pueden tener `TR-2026-000001`; el identificador usado en URLs es un UUID aleatorio.

No se permiten traspasos entre empresas ni entre una sucursal y ella misma.

## 4. Superficies y roles

### 4.1 Panel operativo y empresarial

Es la interfaz normal de administradores de empresa, encargados, conciliadores comerciales y auditores.

### 4.2 Django Admin

Es exclusivo para superusuarios. Los administradores de empresa no reciben acceso aunque tengan responsabilidades administrativas.

### 4.3 Superusuario

- crea empresas y el primer administrador empresarial;
- no crea sucursales, productos, encargados, conciliadores, auditores ni movimientos operativos;
- no participa en preparación, despacho, recepción, conciliación, cierre o anulación;
- consulta globalmente todos los modelos desde Django Admin;
- puede corregir registros existentes indicando una justificación obligatoria;
- no puede eliminar evidencia confirmada;
- no elimina registros operativos;
- toda corrección conserva valores anteriores, posteriores, usuario y fecha.

### 4.4 Administrador de empresa

- ve únicamente su empresa y todas sus sucursales;
- crea y mantiene sucursales, productos y cuentas de usuario empresariales;
- asigna a cada cuenta su rol y, para los encargados, su sucursal;
- consulta movimientos, incidencias, reportes y auditoría empresarial;
- exporta CSV;
- supervisa las conciliaciones pendientes y registradas;
- no crea, prepara, despacha, recibe, resuelve, cierra ni anula traspasos.

### 4.5 Conciliador comercial

- pertenece a una empresa y no a una sucursal;
- consulta todos los movimientos, cantidades, evidencias, incidencias y reportes de su empresa;
- filtra movimientos pendientes o registrados en el sistema comercial;
- registra la referencia y fecha del sistema comercial;
- corrige una conciliación indicando un motivo auditado;
- no crea, prepara, despacha, recibe, resuelve, cierra ni anula traspasos;
- no administra empresas, sucursales, productos, usuarios ni permisos.

### 4.6 Encargado

- pertenece a una empresa y una sucursal;
- una sucursal puede tener varios encargados;
- recibe operación completa por defecto;
- es el único rol que puede confirmar definitivamente una recepción;
- consulta movimientos donde su sucursal sea origen o destino.

### 4.7 Auditor

- pertenece a una empresa y no a una sucursal;
- consulta todos los movimientos, cantidades, evidencias, incidencias, conciliaciones, reportes y auditoría de su empresa;
- consulta en modo de solo lectura las sucursales, productos, usuarios y asignaciones de su empresa;
- exporta los reportes y movimientos visibles;
- no crea ni modifica ningún dato operativo, comercial o administrativo;
- no administra empresas, sucursales, productos, usuarios ni permisos.

## 5. Modelos principales

### Company

Código global, nombre, estado y timestamps.

### Branch

Empresa, código único dentro de la empresa, nombre, dirección, teléfono y estado.

### User

La cuenta se crea con nombre de usuario globalmente único, nombre, correo opcional y contraseña. Inicialmente puede quedar pendiente de asignación; el rol y la sucursal se vinculan después desde **Asignaciones**. El superusuario no pertenece a una empresa; el administrador de empresa no pertenece a una sucursal.

### Product

Cada producto solicita únicamente código, nombre y categoría. La empresa y los timestamps son metadatos internos. El código es único dentro de cada empresa. El administrador puede cargar hasta 5.000 productos desde Excel `.xlsx` usando una plantilla descargable. La importación valida el archivo completo antes de escribir: crea códigos nuevos, actualiza nombre y categoría de códigos existentes dentro de la misma empresa y no guarda ninguna fila si encuentra errores.

### Transfer

UUID, empresa, correlativo, origen, destino, estado, observaciones, responsables y timestamps de cada etapa.

### TransferItem

Producto, cantidad enviada con hasta tres decimales y observación. Solo existe una línea por producto.

### Receipt y ReceiptItem

Recepción única por traspaso, editable mientras sea borrador. Conserva cantidades recibidas, productos inesperados, condición dañada y observaciones.

### Evidence

Archivo, tipo, usuario, fecha, nombre original, objeción y relación opcional con una evidencia corregida.

### Incident e IncidentDifference

Un traspaso puede generar una incidencia agrupada con varias diferencias clasificadas como faltante, sobrante, inesperado o dañado.

### CommercialRegistration

Referencia externa, fecha del sistema comercial, observación y conciliador comercial responsable. Es independiente del estado físico.

### Notification y AuditLog

Avisos internos por usuario y registro inmutable de acciones, motivos y cambios.

## 6. Máquina de estados

Flujo normal:

```text
BORRADOR → PREPARADO → DESPACHADO → EN_RECEPCIÓN
                                      ├→ RECIBIDO → CERRADO
                                      └→ RECIBIDO CON DIFERENCIAS
                                           → INCIDENCIA RESUELTA → CERRADO
```

Reglas:

- `BORRADOR` es el único estado donde se modifican destino, productos y cantidades enviadas.
- `PREPARADO` puede volver a `BORRADOR` con motivo auditado.
- `DESPACHADO` exige productos y al menos una evidencia de salida.
- La sucursal destino conoce el traspaso únicamente desde `DESPACHADO`.
- Abrir la recepción crea `EN_RECEPCIÓN` y permite guardar avances.
- Confirmar recepción exige un encargado del destino y evidencia de recepción.
- La confirmación bloquea las cantidades recibidas.
- Una diferencia cuantitativa, daño o producto inesperado crea automáticamente una incidencia agrupada.
- El cierre siempre es manual.
- No puede cerrarse un movimiento con incidencia abierta.
- Un usuario autorizado puede anular cualquier estado anterior a `CERRADO`, incluido un recibido, indicando motivo.
- `CERRADO` y `ANULADO` son terminales para usuarios operativos.

## 7. Evidencias

Se exige al menos una evidencia de salida y una de recepción. Se aceptan JPG, PNG, WEBP y PDF hasta 10 MB.

Los archivos viven en el filesystem y SQLite almacena rutas y metadatos. Cada descarga pasa por autenticación y autorización; no se publica el directorio `media`.

Una evidencia utilizada por una operación confirmada no se elimina. El superusuario puede corregir sus metadatos desde Django Admin con justificación, sin borrar ni reemplazar el archivo original.

## 8. Recepción e incidencias

Al comenzar una recepción se copian las cantidades enviadas como valores iniciales. El usuario puede modificarlas y guardar varias veces antes de confirmar.

Se considera diferencia cuando:

- recibido es menor que enviado;
- recibido es mayor que enviado;
- se registra un producto no enviado;
- un producto se marca como dañado, aunque la cantidad coincida.

Los daños se explican mediante observación; la V1 no captura una cantidad dañada separada.

Resolver una incidencia exige un tipo de resolución y explicación. La evidencia adicional es opcional.

## 9. Conciliación comercial

Después de confirmar recepción, el conciliador comercial puede marcar que el movimiento ya fue registrado en el sistema comercial principal.

Se exige:

- referencia externa;
- fecha externa;
- usuario y timestamp automáticos;
- observación opcional.

Corregir referencia o fecha requiere motivo y conserva el antes/después en auditoría. Conciliar no recibe, cierra ni modifica el estado físico del traspaso. El estado, la referencia, la fecha y el responsable de la conciliación son informativos y visibles para quienes pueden consultar el movimiento.

## 10. Dashboard, reportes y avisos

El dashboard de sucursal muestra pendientes de preparar, despachar, recibir, diferencias, conciliaciones y actividad reciente. El administrador empresarial ve el resumen global; el conciliador comercial ve todas las conciliaciones pendientes de su empresa.

Los reportes permiten filtrar por código/producto, estado y sucursal según alcance. El CSV aplica exactamente los mismos filtros y políticas multiempresa.

Los encargados reciben avisos operativos, el administrador empresarial recibe excepciones como diferencias y anulaciones, y los conciliadores comerciales reciben los movimientos pendientes de registro comercial.

## 11. Auditoría e inmutabilidad

Se auditan creación, edición, preparación, retorno a borrador, despacho, recepción, incidencias, resolución, cierre, anulación, evidencias, administración empresarial y conciliación.

La línea temporal de un traspaso es visible para quienes pueden consultar ese traspaso. La auditoría general se limita a empresa y sucursal; el superusuario tiene alcance global desde Django Admin.

Los registros y evidencias se conservan indefinidamente en V1.

## 12. Seguridad

- autenticación obligatoria y sin registro público;
- contraseñas administradas por Django;
- protección CSRF;
- autorización backend en cada operación;
- UUID no enumerables;
- validación de empresa, sucursal, estado y rol;
- validación de extensión y tamaño de archivos;
- mensajes genéricos y respuestas 404 para objetos fuera del alcance;
- Django Admin bloqueado para usuarios que no sean superusuarios.

## 13. Ejecución local

Docker Compose ejecuta un servicio Django y persiste SQLite y evidencias en un volumen. El contenedor aplica migraciones al iniciar.

El despliegue productivo, HTTPS, proxy, backups externos y migración a PostgreSQL se definirán antes de publicar el sistema fuera de un entorno local.

## 14. Criterios de aceptación

La V1 se considera funcional cuando:

1. Dos empresas pueden operar sin observar datos, URLs, archivos, reportes o auditoría entre ellas.
2. Un encargado crea y prepara un traspaso con productos y fotografía.
3. Un usuario autorizado confirma la salida y el destino recibe el aviso.
4. El destino guarda avance y un encargado confirma la recepción con fotografía.
5. Una recepción exacta queda recibida y requiere cierre manual.
6. Faltantes, sobrantes, daños o productos inesperados generan una incidencia agrupada.
7. La incidencia debe resolverse antes del cierre.
8. El conciliador comercial registra la referencia del sistema principal sin cambiar el estado físico, y los encargados pueden consultarla.
9. CSV, evidencias y auditoría respetan el alcance de empresa y sucursal.
10. El historial permite reconstruir responsables, cantidades, timestamps, evidencias y correcciones.
11. Un auditor consulta toda la información de su empresa sin poder modificar datos ni acceder a otra empresa.
12. El administrador importa productos desde Excel sin afectar otra empresa y sin generar cargas parciales cuando el archivo contiene errores.
