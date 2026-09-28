# Correcciones y verificación — 28 de septiembre de 2026

Se completó la implementación iniciada el 25 de septiembre y se verificó el código actual. El informe original conserva la evidencia previa; sus probes reproducen defectos antiguos y no deben usarse como criterio de aceptación del código corregido.

## Resultado

- A01–A02: edición y transiciones comparten bloqueo del traspaso hasta completar validación, guardado y auditoría. Dos pruebas con conexiones PostgreSQL reales verifican espera por bloqueo y resultados consistentes.
- A03: productos inesperados se validan con su tipo correcto; cantidad obligatoria y rechazo de duplicados de productos enviados.
- A04: backend de autenticación y servicios comprueban empresa/sucursal activa. Las sesiones rechazadas se eliminan en la siguiente solicitud.
- A05: snapshots de usuario usan una lista de campos permitidos. La migración `0010` retira los hashes existentes de los JSON de auditoría; no modifica contraseñas de cuentas.
- A06–A07: CSV neutraliza prefijos de fórmula; inicio de recepción y apertura de avisos requieren POST y CSRF.
- A08–A10: filtros inválidos responden 400; duplicados de catálogo y libros inválidos presentan errores de formulario. Excel limita descompresión, dimensiones y elementos XML, y rechaza DTD/entidades.
- A11–A13: indicadores cuentan los estados correspondientes; correos agotados salen de PROCESSING; los hilos de pruebas cierran sus conexiones y el desmontaje de PostgreSQL termina correctamente.
- Login: presupuesto persistente compartido entre los accesos operativo y técnico, con rechazo 429; se registran fallos sin credenciales.
- Producción: clave obligatoria y valores HTTPS seguros; puerto publicado solo en loopback. El entrypoint comprueba seguridad antes de migrar, exceptuando únicamente las políticas opcionales HSTS de subdominios y precarga.
- Dependencias fijadas con hashes; activos web locales y versionados con licencias. Documentación de PostgreSQL externo y respaldos corregida.

## Comprobaciones ejecutadas

| Comprobación | Resultado |
| --- | --- |
| Suite completa SQLite | 62 pruebas: 60 pasan y 2 de bloqueo se omiten; la nueva prueba adicional de configuración de producción pasa por separado |
| Suite final PostgreSQL 16, Django 5.2.17 | 63/63 pasan, con eliminación correcta de la base temporal |
| Migraciones de modelos | `makemigrations --check --dry-run`: sin cambios pendientes |
| Dependencias | `pip check`: sin incompatibilidades; `pip-audit`: sin avisos conocidos en los 12 paquetes fijados |
| Imagen Docker | Construida como `gotes-audit-fixed:local`; migraciones, collectstatic y arranque Gunicorn 25.3.0 correctos |
| HTTP en imagen con configuración de producción | Login y cinco recursos estáticos locales responden 200 |
| Navegador Chromium aislado | Login, inicio POST, cantidades, producto inesperado, evidencia y confirmación completados; sin errores JavaScript ni peticiones externas; captura móvil revisada |
| Revisión del diff | Sin errores de espacios en `git diff --check` |

Evidencia: [PostgreSQL](verificacion-postgres-2026-09-28.txt), [dependencias](dependencias-corregidas-2026-09-28.json). Las pruebas de regresión están en `core/tests/test_security.py`.

## Por qué existen dos archivos de dependencias

`requirements.in` contiene las dependencias directas y los rangos permitidos para mantenimiento. `requirements.txt` es el resultado generado: fija también las dependencias transitivas y sus hashes. Docker y la instalación normal leen únicamente `requirements.txt`. No se deben instalar ambos archivos ni editar manualmente el archivo generado. Se verificó que las versiones fijadas satisfacen todos los rangos de `.in`.

## Aplicación en el servidor

Este trabajo modifica y prueba el repositorio; no desplegó sobre producción ni cambió sus datos o secretos. Al desplegar, seguir README: respaldar base y evidencias, configurar la clave y HTTPS, reconstruir la imagen y aplicar las migraciones `0010` y `0011`. Los usuarios deberán iniciar sesión nuevamente por el cambio de backend.

Verificar que el proxy sobrescriba cabeceras reenviadas y limite login por cliente. El limitador interno usa REMOTE_ADDR deliberadamente; detrás de un proxy, su presupuesto se comparte y debe dimensionarse según esa topología. La red `nr-net` debe tener acceso controlado. Los respaldos antiguos pueden conservar hashes de auditoría y requieren acceso restringido y retención apropiada. No se probó el firewall ni el SMTP reales del servidor. Las pruebas y el análisis de dependencias reducen riesgos; no garantizan ausencia absoluta de defectos.
