# Carga de evidencias desde celular

Se corrigieron dos carencias verificadas: ausencia de progreso/límite de espera en el envío y pérdida del detalle del error de validación al volver a recepción. El límite del servidor es 5 MB por defecto; fotos mayores o formatos no admitidos podían producir una experiencia ambigua. No se ha identificado todavía el modelo/navegador del dispositivo reportado, ni se ha inspeccionado su proxy o una foto original: no se atribuye una causa única a ese caso.

## Cambios

- Mejora progresiva en `core/static/core/evidence-upload.js`, compartida por salida y recepción.
- Optimiza fotos mayores al objetivo de 750 KB antes de enviarlas: JPG, lado máximo 1920 px, intentos de calidad acotados. Nunca amplía imágenes. No modifica PDF. Rechaza claramente HEIC/HEIF y originales de más de 30 MB; no relaja formatos ni validación del servidor.
- Indica preparación, porcentaje enviado y espera de confirmación. La preparación tiene límites de 15 segundos por etapa y la petición de red 60 segundos. En error se restaura el botón, incluido el botón externo al formulario de recepción, conservando el archivo seleccionado.
- Distingue rechazo de tamaño HTTP 413, sesión/permisos, formato inválido, desconexión y tiempo agotado. No reintenta automáticamente; tras un fallo de red advierte que se debe verificar si ya se guardó.
- La ruta de carga ofrece JSON cuando se solicita expresamente y conserva POST/CSRF, autorización y bloqueo transaccional. El formulario tradicional sigue funcionando sin JavaScript y conserva el motivo del error.

## Verificación

- 67 pruebas Django pasan en PostgreSQL; SQLite pasa 65 y omite las dos de bloqueo.
- Chromium con emulación Pixel 7: una imagen sintética JPG de 11.624.598 bytes se optimizó y guardó en 430.020 bytes. La consulta a la base y al almacenamiento temporal confirmó una única evidencia de recepción.
- Probados rechazo HEIC, HTTP 413, fallo de red y timeout: mensajes visibles y botón habilitado después de cada error. El timeout se acortó únicamente en el navegador de pruebas para verificar su manejador; en la aplicación es de 60 segundos.
- Navegación a confirmación solo tras respuesta positiva del servidor; sin errores JavaScript. Captura móvil revisada.
- No se probó la cámara de un teléfono físico. WebKit no pudo ejecutarse por dependencias del sistema ausentes; no se afirma validación de Safari/iOS.

Para aplicar en el servidor se requiere reconstruir y desplegar la aplicación y sus estáticos. Si persiste HTTP 413, revisar el límite del proxy; si el navegador del teléfono devuelve HEIC, exportar JPG o usar el modo compatible de cámara. La optimización guarda una copia comprimida, por lo que debe comprobarse la legibilidad de textos pequeños de la evidencia.
