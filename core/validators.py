from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_EVIDENCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_CONTENT_TYPES = {
    ".jpg": {"image/jpeg", "image/pjpeg"},
    ".jpeg": {"image/jpeg", "image/pjpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
}
SIGNATURES = {
    ".jpg": lambda header: header.startswith(b"\xff\xd8\xff"),
    ".jpeg": lambda header: header.startswith(b"\xff\xd8\xff"),
    ".png": lambda header: header.startswith(b"\x89PNG\r\n\x1a\n"),
    ".webp": lambda header: header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    ".pdf": lambda header: header.startswith(b"%PDF"),
}


def validate_evidence_content_type(upload):
    """Validate the browser-provided MIME type while it is still available."""
    extension = Path(upload.name).suffix.lower()
    content_type = getattr(upload, "content_type", "")
    if (
        extension in ALLOWED_CONTENT_TYPES
        and content_type
        and content_type != "application/octet-stream"
        and content_type not in ALLOWED_CONTENT_TYPES[extension]
    ):
        raise ValidationError("El tipo de archivo no coincide con su extensión.")


def validate_evidence_file(upload):
    extension = Path(upload.name).suffix.lower()
    if extension not in ALLOWED_EVIDENCE_EXTENSIONS:
        raise ValidationError("Formato no permitido. Usa JPG, PNG, WEBP o PDF.")
    max_size_mb = settings.EVIDENCE_MAX_FILE_SIZE_MB
    if upload.size <= 0:
        raise ValidationError("El archivo está vacío.")
    if upload.size > max_size_mb * 1024 * 1024:
        raise ValidationError(f"El archivo supera el límite de {max_size_mb} MB.")
    validate_evidence_content_type(upload)
    position = upload.tell()
    header = upload.read(12)
    upload.seek(position)
    if not SIGNATURES[extension](header):
        raise ValidationError("El contenido del archivo no coincide con su formato.")
