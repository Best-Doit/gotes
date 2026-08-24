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

Abre `http://IP-DEL-SERVIDOR:8009/` si se usará directamente. En ese caso configura las variables `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`, `DJANGO_CSRF_COOKIE_SECURE` y `DJANGO_TRUST_PROXY_HEADERS` en `0` hasta disponer de HTTPS.

Para un dominio con Nginx, Caddy, Traefik o Cloudflare Tunnel, dirige el proxy a `http://127.0.0.1:8009`, conserva las opciones seguras de `.env.prod.example` y establece el dominio real en `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` y `GOTES_PUBLIC_URL`.

Comandos operativos:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web email_worker
docker compose -f docker-compose.prod.yml exec web python manage.py check --deploy
```

Los volúmenes `gotes_postgres_data` y `gotes_media` conservan la base y las evidencias. El Compose de producción inicia una base PostgreSQL nueva; los datos existentes de SQLite no se migran automáticamente.

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

## Interfaces

- `/`: panel operativo y administración empresarial.
- `/django-admin/`: administración técnica y correcciones auditadas, exclusivamente para superusuarios.
- `/auditoria/`: historial filtrado por empresa y sucursal.
- Productos incluye un modal para la carga transaccional del catálogo desde archivos Excel `.xlsx`.

Las evidencias se descargan mediante rutas autenticadas. El directorio de archivos no se publica directamente.
# gotes
