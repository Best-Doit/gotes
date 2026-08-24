import uuid
from decimal import Decimal
from pathlib import Path
from time import sleep

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import IntegrityError, OperationalError, connection, models, transaction
from django.db.models import Q
from django.utils import timezone

from .validators import validate_evidence_file


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Company(TimestampedModel):
    code = models.SlugField(max_length=30, unique=True, verbose_name="código")
    name = models.CharField(max_length=160, verbose_name="nombre")
    is_active = models.BooleanField(default=True, verbose_name="activa")

    class Meta:
        ordering = ("name",)
        verbose_name = "empresa"
        verbose_name_plural = "empresas"

    def __str__(self):
        return self.name


class Branch(TimestampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="branches", verbose_name="empresa")
    code = models.CharField(max_length=30, verbose_name="código")
    name = models.CharField(max_length=160, verbose_name="nombre")
    address = models.CharField(max_length=255, blank=True, verbose_name="dirección")
    phone = models.CharField(max_length=40, blank=True, verbose_name="teléfono")
    is_active = models.BooleanField(default=True, verbose_name="activa")

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=("company", "code"), name="unique_branch_code_per_company")]
        verbose_name = "sucursal"
        verbose_name_plural = "sucursales"

    def __str__(self):
        return f"{self.code} — {self.name}"


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = "SUPERADMIN", "Superusuario"
        COMPANY_ADMIN = "COMPANY_ADMIN", "Administrador de empresa"
        MANAGER = "MANAGER", "Encargado"
        RECONCILER = "RECONCILER", "Conciliador comercial"
        AUDITOR = "AUDITOR", "Auditor"

    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT, related_name="users", verbose_name="empresa")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="users", verbose_name="sucursal")
    role = models.CharField(max_length=20, choices=Role.choices, blank=True, default="", verbose_name="rol")
    phone = models.CharField(max_length=40, blank=True, verbose_name="teléfono")
    allow_dispatch = models.BooleanField(null=True, blank=True, verbose_name="puede despachar")
    allow_close = models.BooleanField(null=True, blank=True, verbose_name="puede cerrar")
    allow_cancel = models.BooleanField(null=True, blank=True, verbose_name="puede anular")
    allow_resolve_incident = models.BooleanField(null=True, blank=True, verbose_name="puede resolver incidencias")

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def clean(self):
        super().clean()
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError({"branch": "La sucursal debe pertenecer a la empresa del usuario."})
        if self.role == self.Role.SUPERADMIN or self.is_superuser:
            if self.company_id or self.branch_id:
                raise ValidationError("Un superusuario no pertenece a una empresa o sucursal.")
            if self.role == self.Role.SUPERADMIN and not self.is_superuser:
                raise ValidationError({"role": "El rol Superusuario requiere una cuenta superusuario de Django."})
        elif not self.role:
            if not self.company_id or self.branch_id:
                raise ValidationError("Un usuario pendiente de asignación requiere empresa y no debe tener sucursal.")
        elif self.role in {self.Role.COMPANY_ADMIN, self.Role.RECONCILER, self.Role.AUDITOR}:
            if not self.company_id or self.branch_id:
                raise ValidationError("Este rol requiere empresa y no debe tener sucursal.")
        elif not self.company_id or not self.branch_id:
            raise ValidationError("Los encargados requieren empresa y sucursal.")

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.SUPERADMIN
            self.is_staff = True
            self.company = None
            self.branch = None
        super().save(*args, **kwargs)

    @property
    def is_company_admin(self):
        return self.role == self.Role.COMPANY_ADMIN

    @property
    def is_commercial_reconciler(self):
        return self.role == self.Role.RECONCILER

    @property
    def is_auditor(self):
        return self.role == self.Role.AUDITOR

    @property
    def has_company_scope(self):
        return self.is_company_admin or self.is_commercial_reconciler or self.is_auditor

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_operational(self):
        return self.is_manager

    def has_capability(self, capability):
        if self.is_superuser:
            return False
        if capability == "reconcile":
            return self.is_commercial_reconciler
        if not self.is_operational:
            return False
        if capability == "receive":
            return self.is_manager
        if capability == "prepare":
            return True
        field = {
            "dispatch": "allow_dispatch",
            "close": "allow_close",
            "cancel": "allow_cancel",
            "resolve_incident": "allow_resolve_incident",
        }.get(capability)
        if not field:
            return False
        override = getattr(self, field)
        return self.is_manager if override is None else override


class Product(TimestampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="products", verbose_name="empresa")
    code = models.CharField(max_length=60, verbose_name="código")
    name = models.CharField(max_length=200, verbose_name="nombre")
    category = models.CharField(max_length=100, verbose_name="categoría")

    class Meta:
        ordering = ("name",)
        constraints = [models.UniqueConstraint(fields=("company", "code"), name="unique_product_code_per_company")]
        verbose_name = "producto"
        verbose_name_plural = "productos"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Sequence(models.Model):
    class Kind(models.TextChoices):
        TRANSFER = "TRANSFER", "Traspaso"
        INCIDENT = "INCIDENT", "Incidencia"

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="sequences")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    year = models.PositiveSmallIntegerField()
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("company", "kind", "year"), name="unique_company_kind_year_sequence")]

    @classmethod
    def take(cls, company, kind, year):
        for attempt in range(20):
            try:
                with transaction.atomic():
                    sequence, _ = cls.objects.get_or_create(company=company, kind=kind, year=year)
                    table = connection.ops.quote_name(cls._meta.db_table)
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"UPDATE {table} SET next_value = next_value + 1 WHERE id = %s RETURNING next_value - 1",
                            [sequence.pk],
                        )
                        return cursor.fetchone()[0]
            except (IntegrityError, OperationalError):
                sleep(0.01 * (attempt + 1))
                continue
        raise RuntimeError("No fue posible generar el correlativo.")


class Transfer(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        PREPARED = "PREPARED", "Preparado"
        DISPATCHED = "DISPATCHED", "Despachado"
        RECEIVING = "RECEIVING", "En recepción"
        RECEIVED = "RECEIVED", "Recibido"
        RECEIVED_DIFFERENCES = "RECEIVED_DIFFERENCES", "Recibido con diferencias"
        CLOSED = "CLOSED", "Cerrado"
        CANCELLED = "CANCELLED", "Anulado"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="transfers", verbose_name="empresa")
    year = models.PositiveSmallIntegerField(editable=False)
    sequence = models.PositiveIntegerField(editable=False)
    code = models.CharField(max_length=30, editable=False)
    origin = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="outgoing_transfers", verbose_name="origen")
    destination = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="incoming_transfers", verbose_name="destino")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="estado")
    notes = models.TextField(blank=True, verbose_name="observaciones")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_transfers")
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="prepared_transfers")
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="dispatched_transfers")
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="closed_transfers")
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="cancelled_transfers")
    prepared_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("company", "year", "sequence"), name="unique_transfer_sequence_per_company_year"),
            models.CheckConstraint(condition=~Q(origin=models.F("destination")), name="different_transfer_branches"),
        ]
        indexes = [models.Index(fields=("company", "status", "created_at"))]
        verbose_name = "traspaso"
        verbose_name_plural = "traspasos"

    def __str__(self):
        return self.code

    def clean(self):
        if self.origin_id and self.destination_id:
            if self.origin_id == self.destination_id:
                raise ValidationError({"destination": "El destino debe ser diferente del origen."})
            if self.origin.company_id != self.destination.company_id:
                raise ValidationError("No se permiten traspasos entre empresas.")
            if self.company_id and self.origin.company_id != self.company_id:
                raise ValidationError("Las sucursales deben pertenecer a la empresa del traspaso.")

    def save(self, *args, **kwargs):
        if not self.pk and not self.sequence:
            self.year = timezone.localdate().year
            self.sequence = Sequence.take(self.company, Sequence.Kind.TRANSFER, self.year)
            self.code = f"TR-{self.year}-{self.sequence:06d}"
        super().save(*args, **kwargs)


class TransferItem(TimestampedModel):
    transfer = models.ForeignKey(Transfer, on_delete=models.PROTECT, related_name="items", verbose_name="traspaso")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="transfer_items", verbose_name="producto")
    quantity_sent = models.DecimalField(max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))], verbose_name="cantidad enviada")
    send_note = models.CharField(max_length=255, blank=True, verbose_name="observación")

    class Meta:
        ordering = ("product__name",)
        constraints = [models.UniqueConstraint(fields=("transfer", "product"), name="unique_product_per_transfer")]
        verbose_name = "producto enviado"
        verbose_name_plural = "productos enviados"

    def clean(self):
        if self.transfer_id and self.product_id and self.transfer.company_id != self.product.company_id:
            raise ValidationError("El producto debe pertenecer a la empresa del traspaso.")
        if (
            self.transfer_id
            and not getattr(self, "_allow_historical_correction", False)
            and not Transfer.objects.filter(pk=self.transfer_id, status=Transfer.Status.DRAFT).exists()
        ):
            raise ValidationError("Los productos solo pueden modificarse en borrador.")

    def __str__(self):
        return f"{self.transfer.code}: {self.product.name}"


class Receipt(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        CONFIRMED = "CONFIRMED", "Confirmada"

    transfer = models.OneToOneField(Transfer, on_delete=models.PROTECT, related_name="receipt", verbose_name="traspaso")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="started_receipts")
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="confirmed_receipts")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, verbose_name="observaciones")

    class Meta:
        verbose_name = "recepción"
        verbose_name_plural = "recepciones"

    def __str__(self):
        return f"Recepción {self.transfer.code}"


class ReceiptItem(TimestampedModel):
    receipt = models.ForeignKey(Receipt, on_delete=models.PROTECT, related_name="items", verbose_name="recepción")
    transfer_item = models.OneToOneField(TransferItem, null=True, blank=True, on_delete=models.PROTECT, related_name="receipt_item")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="receipt_items", verbose_name="producto")
    quantity_received = models.DecimalField(max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0"))], verbose_name="cantidad recibida")
    is_unexpected = models.BooleanField(default=False, verbose_name="producto no enviado")
    is_damaged = models.BooleanField(default=False, verbose_name="dañado")
    observation = models.CharField(max_length=255, blank=True, verbose_name="observación")

    class Meta:
        ordering = ("product__name",)
        constraints = [
            models.UniqueConstraint(fields=("receipt", "product"), condition=Q(is_unexpected=True), name="unique_unexpected_product_per_receipt"),
        ]
        verbose_name = "producto recibido"
        verbose_name_plural = "productos recibidos"

    def clean(self):
        if self.receipt_id and self.product_id and self.receipt.transfer.company_id != self.product.company_id:
            raise ValidationError("El producto debe pertenecer a la empresa del traspaso.")
        if self.transfer_item_id:
            if self.transfer_item.transfer_id != self.receipt.transfer_id or self.transfer_item.product_id != self.product_id:
                raise ValidationError("La línea recibida no coincide con el producto enviado.")
            self.is_unexpected = False
        elif not self.is_unexpected:
            raise ValidationError("Una línea sin producto enviado debe marcarse como inesperada.")
        if self.receipt_id and self.receipt.status == Receipt.Status.CONFIRMED and not getattr(self, "_allow_historical_correction", False):
            raise ValidationError("La recepción confirmada no puede modificarse.")


def evidence_upload_path(instance, filename):
    safe_extension = Path(filename).suffix.lower()
    return f"transfers/{instance.transfer.company.code}/{instance.transfer.year}/{instance.transfer.uuid}/{uuid.uuid4().hex}{safe_extension}"


class Evidence(TimestampedModel):
    class Type(models.TextChoices):
        PREPARATION = "PREPARATION", "Preparación"
        DISPATCH = "DISPATCH", "Salida"
        RECEIPT = "RECEIPT", "Recepción"
        INCIDENT = "INCIDENT", "Incidencia"
        CORRECTION = "CORRECTION", "Corrección"

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    transfer = models.ForeignKey(Transfer, on_delete=models.PROTECT, related_name="evidences", verbose_name="traspaso")
    type = models.CharField(max_length=20, choices=Type.choices, verbose_name="tipo")
    file = models.FileField(upload_to=evidence_upload_path, validators=[validate_evidence_file], verbose_name="archivo")
    original_name = models.CharField(max_length=255, editable=False)
    description = models.CharField(max_length=255, blank=True, verbose_name="descripción")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_evidences")
    objected = models.BooleanField(default=False, verbose_name="objetada")
    objection_reason = models.TextField(blank=True, verbose_name="motivo de objeción")
    correction_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="corrections", verbose_name="corrige a")

    class Meta:
        ordering = ("created_at",)
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"

    def save(self, *args, **kwargs):
        if self.file and not self.original_name:
            self.original_name = Path(self.file.name).name
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.transfer.status != Transfer.Status.DRAFT:
            raise ValidationError("Una evidencia confirmada no puede eliminarse.")
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.get_type_display()} — {self.transfer.code}"


class Incident(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Abierta"
        IN_REVIEW = "IN_REVIEW", "En revisión"
        RESOLVED = "RESOLVED", "Resuelta"

    class ResolutionType(models.TextChoices):
        FOUND = "FOUND", "Producto encontrado"
        ACCEPTED = "ACCEPTED", "Diferencia aceptada"
        CORRECTED_EXTERNAL = "CORRECTED_EXTERNAL", "Corregido en sistema comercial"
        RETURNED = "RETURNED", "Producto devuelto"
        OTHER = "OTHER", "Otro"

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="incidents")
    transfer = models.OneToOneField(Transfer, on_delete=models.PROTECT, related_name="incident")
    year = models.PositiveSmallIntegerField(editable=False)
    sequence = models.PositiveIntegerField(editable=False)
    code = models.CharField(max_length=30, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    summary = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_incidents")
    resolution_type = models.CharField(max_length=30, choices=ResolutionType.choices, blank=True)
    resolution_text = models.TextField(blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="resolved_incidents")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("company", "year", "sequence"), name="unique_incident_sequence_per_company_year")]
        verbose_name = "incidencia"
        verbose_name_plural = "incidencias"

    def save(self, *args, **kwargs):
        if not self.pk and not self.sequence:
            self.year = timezone.localdate().year
            self.sequence = Sequence.take(self.company, Sequence.Kind.INCIDENT, self.year)
            self.code = f"INC-{self.year}-{self.sequence:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class IncidentDifference(models.Model):
    class Type(models.TextChoices):
        MISSING = "MISSING", "Faltante"
        SURPLUS = "SURPLUS", "Sobrante"
        UNEXPECTED = "UNEXPECTED", "Producto inesperado"
        DAMAGED = "DAMAGED", "Producto dañado"

    incident = models.ForeignKey(Incident, on_delete=models.PROTECT, related_name="differences")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="incident_differences")
    type = models.CharField(max_length=20, choices=Type.choices)
    quantity_sent = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    quantity_received = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    observation = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("product__name", "type")
        verbose_name = "diferencia"
        verbose_name_plural = "diferencias"


class CommercialRegistration(TimestampedModel):
    transfer = models.OneToOneField(Transfer, on_delete=models.PROTECT, related_name="commercial_registration")
    external_reference = models.CharField(max_length=120, verbose_name="referencia externa")
    external_date = models.DateField(verbose_name="fecha en sistema comercial")
    notes = models.TextField(blank=True, verbose_name="observaciones")
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="commercial_registrations")

    class Meta:
        verbose_name = "registro en sistema comercial"
        verbose_name_plural = "registros en sistema comercial"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    transfer = models.ForeignKey(Transfer, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class EmailOutbox(models.Model):
    class Event(models.TextChoices):
        TRANSFER_DISPATCHED = "TRANSFER_DISPATCHED", "Traspaso despachado"
        TRANSFER_RECEIVED = "TRANSFER_RECEIVED", "Traspaso recibido"
        TRANSFER_RECONCILED = "TRANSFER_RECONCILED", "Traspaso conciliado"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        PROCESSING = "PROCESSING", "En proceso"
        SENT = "SENT", "Enviado"
        FAILED = "FAILED", "Fallido"

    transfer = models.ForeignKey(Transfer, on_delete=models.CASCADE, related_name="email_deliveries")
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_deliveries",
    )
    recipient_email = models.EmailField()
    event = models.CharField(max_length=40, choices=Event.choices)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("transfer", "event", "recipient_email"),
                name="unique_transfer_email_event_recipient",
            ),
        ]
        indexes = [models.Index(fields=("status", "created_at"), name="email_outbox_queue_idx")]
        verbose_name = "correo en bandeja de salida"
        verbose_name_plural = "correos en bandeja de salida"

    def __str__(self):
        return f"{self.get_event_display()} · {self.recipient_email}"


class AuditLog(models.Model):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="audit_logs")
    action = models.CharField(max_length=40, db_index=True)
    object_type = models.CharField(max_length=80)
    object_uuid = models.CharField(max_length=80, db_index=True)
    description = models.TextField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"

    def __str__(self):
        return f"{self.action} {self.object_type} {self.object_uuid}"
