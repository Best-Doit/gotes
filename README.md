# GOTES — Control histórico de traspasos

Aplicación Django multiempresa para documentar despachos y recepciones entre sucursales. No administra inventario ni modifica existencias del sistema comercial.

## Inicio rápido con Docker

```bash
docker compose up --build -d
docker compose exec web python manage.py createsuperuser
```

Abre `http://localhost:8000/django-admin/` con el **Superusuario**, crea una empresa y su primer usuario con rol **Administrador de empresa**. Desde `http://localhost:8000/`, ese administrador crea las cuentas básicas y luego les asigna rol y sucursal en el módulo **Asignaciones**. Los roles disponibles son **Encargado**, **Conciliador comercial** y **Auditor**. El auditor dispone de acceso empresarial de solo lectura.

El Superusuario no participa en la operación. Django Admin le permite ver todos los modelos y corregir registros existentes con una justificación obligatoria y auditada, pero solo puede crear empresas y administradores de empresa.

Los datos de SQLite y las evidencias viven en el volumen persistente de GOTES.

## Producción con Docker

Producción usa PostgreSQL, Gunicorn, WhiteNoise y un worker independiente para los correos. El contenedor web escucha internamente en `8000` y Docker publica la aplicación en el puerto `8009` del servidor.

```bash
cp .env.prod.example .env
# Edita .env y reemplaza dominio, claves y credenciales SMTP.
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

El puerto `8009` se publica únicamente en `127.0.0.1`. Producción requiere HTTPS mediante un proxy; el arranque se detiene si Django detecta advertencias de seguridad, salvo las opciones voluntarias de HSTS para subdominios y precarga. Genera `DJANGO_SECRET_KEY` con `python -c 'import secrets; print(secrets.token_urlsafe(64))'` y conserva esa clave entre despliegues.

Para un dominio con Nginx, Caddy, Traefik o Cloudflare Tunnel, dirige el proxy a `http://127.0.0.1:8009`, conserva las opciones seguras de `.env.prod.example` y establece el dominio real en `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` y `GOTES_PUBLIC_URL`.

Comandos operativos:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web email_worker
docker compose -f docker-compose.prod.yml exec web python manage.py check --deploy
```

Antes del arranque deben existir la red Docker externa `nr-net`, un PostgreSQL accesible como `postgres-global`, y la base y el usuario configurados en `.env`. Este Compose no crea ni respalda PostgreSQL. El volumen `gotes_media` conserva las evidencias; respalda además la base externa con su procedimiento de `pg_dump` y verifica restauraciones de ambos conjuntos. Los datos existentes de SQLite no se migran automáticamente.

El proxy debe eliminar las cabeceras reenviadas del cliente y establecer `X-Forwarded-Proto` y `X-Forwarded-Host` con sus propios valores. No expongas el backend directamente. Si el proxy está en otro contenedor, debe acceder por una red privada controlada; revisa qué otros contenedores comparten `nr-net`.

Al desplegar esta corrección, `migrate` aplica `0010` (retira hashes de contraseña de los snapshots de auditoría) y `0011` (crea el limitador de login). Las copias de respaldo antiguas mantienen su contenido y necesitan la política de acceso y retención correspondiente. El cambio de backend de autenticación invalida las sesiones previas: los usuarios deberán volver a iniciar sesión.

## Notificaciones por correo

GOTES genera correos para los encargados activos de las sucursales de origen y destino cuando se confirma la salida, cuando se confirma la recepción y cuando se registra la conciliación comercial. Los conciliadores reciben un aviso anticipado al confirmar la salida y otro correo de acción requerida cuando la recepción queda confirmada. Solo se incluyen usuarios activos con un correo registrado.

El envío usa una bandeja de salida transaccional: la operación guarda primero el correo pendiente en la base de datos y el servicio `email_worker` lo envía después. Así, una caída temporal del proveedor no revierte el traspaso y el correo puede reintentarse hasta cinco veces.

En desarrollo los mensajes se imprimen en la consola. Para usar SMTP, copia `.env.example` a `.env`, completa el proveedor y reinicia los servicios:

```bash
cp .env.example .env
docker compose up --build -d
```

Si ejecutas Django sin Docker, mantén el procesador en una segunda terminal:

```bash
python manage.py send_notification_emails --watch --interval 30
```

La variable `GOTES_PUBLIC_URL` debe contener la dirección pública de la aplicación para que los enlaces de los correos sean correctos. Las entregas y sus errores se consultan en Django Admin, en **Correos en bandeja de salida**.

Si `DJANGO_DEFAULT_FROM_EMAIL` queda vacío, GOTES usa automáticamente la cuenta SMTP autenticada como remitente. Para Google, el usuario debe ser el correo completo y la contraseña debe ser una contraseña de aplicación.

Las evidencias permiten JPG/JPEG, PNG, WEBP y PDF. El límite predeterminado es 5 MB y puede ajustarse con `GOTES_EVIDENCE_MAX_FILE_SIZE_MB`.

En el navegador, las fotos grandes se convierten a JPG con un lado máximo de 1920 píxeles y un objetivo de 750 KB antes de subirlas; la evidencia guardada es esa versión optimizada. El archivo original permanece en el dispositivo. Los PDF se envían sin conversión y conservan el límite configurado. Fotos de más de 30 MB o HEIC/HEIF requieren seleccionar/exportar una imagen JPG de menor tamaño. La carga muestra progreso, espera confirmación del servidor y libera el botón si falla; después de una pérdida de conexión se debe revisar el traspaso antes de repetir el envío, porque el servidor podría haberlo guardado.

## Inicio sin Docker

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Por defecto la base y los archivos se guardan dentro de `.data/`. Se pueden cambiar mediante `GOTES_DATA_DIR` y `GOTES_MEDIA_ROOT`. Las variables anteriores con prefijo `GOTS_` siguen aceptándose temporalmente para facilitar la migración.

## Verificación

```bash
python manage.py check
python manage.py test
```

Las pruebas de concurrencia se ejecutan con PostgreSQL; SQLite no proporciona los mismos bloqueos de filas y se reserva para desarrollo. Para una verificación aislada:

```bash
docker build -t gotes-audit-fixed:local .
bash docs/auditoria/postgres-check.sh
```

Las dependencias están fijadas con hashes en `requirements.txt`; `requirements.in` contiene los rangos de mantenimiento. Actualiza el archivo fijado con `pip-compile --generate-hashes --upgrade --output-file requirements.txt requirements.in`, revisa los cambios y ejecuta las pruebas y el análisis de dependencias antes de desplegar. Usa `.venv/bin/python` para trabajar con las versiones instaladas para este proyecto.

Los dos accesos de login comparten un límite de 30 solicitudes POST por dirección del par de conexión cada 15 minutos. Puede ajustarse mediante `GOTES_LOGIN_RATE_MAX_ATTEMPTS` y `GOTES_LOGIN_RATE_WINDOW_SECONDS`. No se confía en `X-Forwarded-For`: detrás de un proxy, este límite puede compartirse entre sus usuarios. Configura además el límite por cliente en el proxy y dimensiona el límite interno para esa topología. Los intentos fallidos y rechazos se registran sin credenciales.

Suspender una empresa o sucursal bloquea el acceso de sus usuarios y elimina sus sesiones en la siguiente solicitud; el superusuario técnico conserva acceso para administrar la suspensión. La recepción se inicia mediante POST con CSRF. Los filtros inválidos responden 400 y los errores de carga/catálogos se presentan en los formularios.

Los activos de interfaz están versionados en `core/static/core/vendor`, con licencias y hashes en `manifest.json`; no requieren un CDN para cargar el login. Excel acepta hasta 5 MB comprimidos, 25 MB descomprimidos, 5.000 productos, 10.001 filas totales y 100 columnas. Se rechazan DTD y entidades XML.

## Interfaces

- `/`: panel operativo y administración empresarial.
- `/django-admin/`: administración técnica y correcciones auditadas, exclusivamente para superusuarios.
- `/auditoria/`: historial filtrado por empresa y sucursal.
- Productos incluye un modal para la carga transaccional del catálogo desde archivos Excel `.xlsx`.

Las evidencias se descargan mediante rutas autenticadas. El directorio de archivos no se publica directamente.
# gotes
