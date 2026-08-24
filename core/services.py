import json
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.utils import timezone

from .email_notifications import (
    queue_transfer_dispatched_emails,
    queue_transfer_received_emails,
    queue_transfer_reconciled_emails,
)
from .models import (
    AuditLog,
    CommercialRegistration,
    Evidence,
    Incident,
    IncidentDifference,
    Notification,
    Receipt,
    ReceiptItem,
    Transfer,
    User,
)


DESTINATION_VISIBLE_STATUSES = (
    Transfer.Status.DISPATCHED,
    Transfer.Status.RECEIVING,
    Transfer.Status.RECEIVED,
    Transfer.Status.RECEIVED_DIFFERENCES,
    Transfer.Status.CLOSED,
    Transfer.Status.CANCELLED,
)


def visible_transfers(user):
    queryset = Transfer.objects.select_related(
        "company", "origin", "destination", "created_by", "commercial_registration__registered_by"
    )
    if user.is_superuser:
        return queryset
    if not user.company_id:
        return queryset.none()
    queryset = queryset.filter(company_id=user.company_id)
    if user.has_company_scope:
        return queryset
    if not user.branch_id:
        return queryset.none()
    return queryset.filter(
        Q(origin_id=user.branch_id) |
        Q(destination_id=user.branch_id, status__in=DESTINATION_VISIBLE_STATUSES)
    )


def snapshot(instance):
    data = model_to_dict(instance)
    return json.loads(json.dumps(data, default=str))


def audit(*, user, action, instance, description, request=None, before=None, after=None, reason=""):
    company = getattr(instance, "company", None)
    if company is None and hasattr(instance, "transfer"):
        company = instance.transfer.company
    branch = user.branch if user and user.branch_id else None
    object_uuid = getattr(instance, "uuid", None) or getattr(instance, "code", None) or instance.pk
    return AuditLog.objects.create(
        company=company,
        branch=branch,
        user=user if user and user.is_authenticated else None,
        action=action,
        object_type=instance._meta.label,
        object_uuid=str(object_uuid),
        description=description,
        before=before,
        after=after,
        reason=reason,
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255] if request else "",
    )


def _lock_transfer(transfer):
    return Transfer.objects.select_for_update().select_related("origin", "destination", "company").get(pk=transfer.pk)


def _ensure_branch_action(user, transfer, capability, *, destination=False):
    if not user.is_operational or user.company_id != transfer.company_id:
        raise PermissionDenied
    expected_branch = transfer.destination_id if destination else transfer.origin_id
    if user.branch_id != expected_branch or not user.has_capability(capability):
        raise PermissionDenied


def notify_managers(branch, message, transfer):
    users = User.objects.filter(company=branch.company, branch=branch, role=User.Role.MANAGER, is_active=True)
    Notification.objects.bulk_create([Notification(user=user, transfer=transfer, message=message) for user in users])


def notify_company_admins(company, message, transfer):
    users = User.objects.filter(company=company, role=User.Role.COMPANY_ADMIN, is_active=True)
    Notification.objects.bulk_create([Notification(user=user, transfer=transfer, message=message) for user in users])


def notify_commercial_reconcilers(company, message, transfer):
    users = User.objects.filter(company=company, role=User.Role.RECONCILER, is_active=True)
    Notification.objects.bulk_create([Notification(user=user, transfer=transfer, message=message) for user in users])


@transaction.atomic
def prepare_transfer(transfer, user, request=None):
    transfer = _lock_transfer(transfer)
    _ensure_branch_action(user, transfer, "prepare")
    if transfer.status != Transfer.Status.DRAFT:
        raise ValidationError("Solo un borrador puede marcarse como preparado.")
    if not transfer.items.exists():
        raise ValidationError("Agrega al menos un producto.")
    transfer.status = Transfer.Status.PREPARED
    transfer.prepared_by = user
    transfer.prepared_at = timezone.now()
    transfer.save(update_fields=("status", "prepared_by", "prepared_at", "updated_at"))
    audit(user=user, action="PREPARE", instance=transfer, description=f"{user} confirmó la preparación.", request=request)
    return transfer


@transaction.atomic
def return_to_draft(transfer, user, reason, request=None):
    transfer = _lock_transfer(transfer)
    _ensure_branch_action(user, transfer, "prepare")
    if transfer.status != Transfer.Status.PREPARED:
        raise ValidationError("Solo un traspaso preparado puede volver a borrador.")
    if not reason.strip():
        raise ValidationError("Debes indicar el motivo.")
    transfer.status = Transfer.Status.DRAFT
    transfer.prepared_by = None
    transfer.prepared_at = None
    transfer.save(update_fields=("status", "prepared_by", "prepared_at", "updated_at"))
    audit(user=user, action="RETURN_DRAFT", instance=transfer, description="El traspaso volvió a borrador.", request=request, reason=reason)
    return transfer


@transaction.atomic
def dispatch_transfer(transfer, user, request=None):
    transfer = _lock_transfer(transfer)
    _ensure_branch_action(user, transfer, "dispatch")
    if transfer.status != Transfer.Status.PREPARED:
        raise ValidationError("Solo un traspaso preparado puede despacharse.")
    if not transfer.items.exists():
        raise ValidationError("El traspaso no tiene productos.")
    if not transfer.evidences.filter(type=Evidence.Type.DISPATCH).exists():
        raise ValidationError("Adjunta al menos una evidencia de salida.")
    transfer.status = Transfer.Status.DISPATCHED
    transfer.dispatched_by = user
    transfer.dispatched_at = timezone.now()
    transfer.save(update_fields=("status", "dispatched_by", "dispatched_at", "updated_at"))
    audit(user=user, action="DISPATCH", instance=transfer, description=f"{user} confirmó la salida física.", request=request)
    notify_managers(transfer.destination, f"{transfer.code} está pendiente de recepción.", transfer)
    queue_transfer_dispatched_emails(transfer)
    return transfer


@transaction.atomic
def get_or_start_receipt(transfer, user, request=None):
    transfer = _lock_transfer(transfer)
    if not user.is_operational or user.company_id != transfer.company_id or user.branch_id != transfer.destination_id:
        raise PermissionDenied
    if transfer.status not in {Transfer.Status.DISPATCHED, Transfer.Status.RECEIVING}:
        raise ValidationError("Este traspaso no está disponible para recepción.")
    receipt, created = Receipt.objects.get_or_create(transfer=transfer, defaults={"started_by": user})
    if created:
        ReceiptItem.objects.bulk_create([
            ReceiptItem(
                receipt=receipt,
                transfer_item=item,
                product=item.product,
                quantity_received=item.quantity_sent,
            ) for item in transfer.items.select_related("product")
        ])
        transfer.status = Transfer.Status.RECEIVING
        transfer.save(update_fields=("status", "updated_at"))
        audit(user=user, action="START_RECEIPT", instance=transfer, description=f"{user} inició la recepción.", request=request)
    return receipt


@transaction.atomic
def confirm_receipt(transfer, user, request=None):
    transfer = _lock_transfer(transfer)
    _ensure_branch_action(user, transfer, "receive", destination=True)
    if transfer.status != Transfer.Status.RECEIVING:
        raise ValidationError("La recepción no está en borrador.")
    receipt = Receipt.objects.select_for_update().get(transfer=transfer)
    if receipt.status == Receipt.Status.CONFIRMED:
        raise ValidationError("La recepción ya fue confirmada.")
    if not transfer.evidences.filter(type=Evidence.Type.RECEIPT).exists():
        raise ValidationError("Adjunta al menos una evidencia de recepción.")
    expected_ids = set(transfer.items.values_list("id", flat=True))
    received_ids = set(receipt.items.filter(is_unexpected=False).values_list("transfer_item_id", flat=True))
    if expected_ids != received_ids:
        raise ValidationError("Debes registrar la cantidad recibida de todos los productos enviados.")

    differences = []
    for item in receipt.items.select_related("product", "transfer_item"):
        if item.is_unexpected:
            if item.quantity_received > 0:
                differences.append((item, IncidentDifference.Type.UNEXPECTED, Decimal("0")))
            continue
        sent = item.transfer_item.quantity_sent
        if item.quantity_received < sent:
            differences.append((item, IncidentDifference.Type.MISSING, sent))
        elif item.quantity_received > sent:
            differences.append((item, IncidentDifference.Type.SURPLUS, sent))
        if item.is_damaged:
            differences.append((item, IncidentDifference.Type.DAMAGED, sent))

    now = timezone.now()
    receipt.status = Receipt.Status.CONFIRMED
    receipt.confirmed_by = user
    receipt.confirmed_at = now
    receipt.save(update_fields=("status", "confirmed_by", "confirmed_at", "updated_at"))
    transfer.received_at = now
    transfer.status = Transfer.Status.RECEIVED_DIFFERENCES if differences else Transfer.Status.RECEIVED
    transfer.save(update_fields=("status", "received_at", "updated_at"))

    if differences:
        incident = Incident.objects.create(
            company=transfer.company,
            transfer=transfer,
            created_by=user,
            summary="Diferencias detectadas durante la recepción.",
        )
        IncidentDifference.objects.bulk_create([
            IncidentDifference(
                incident=incident,
                product=item.product,
                type=difference_type,
                quantity_sent=sent,
                quantity_received=item.quantity_received,
                observation=item.observation,
            ) for item, difference_type, sent in differences
        ])
        audit(user=user, action="INCIDENT", instance=incident, description=f"Se creó {incident.code} automáticamente.", request=request)
        notify_managers(transfer.origin, f"{transfer.code} fue recibido con diferencias.", transfer)
        notify_managers(transfer.destination, f"{transfer.code} fue recibido con diferencias.", transfer)
        notify_company_admins(transfer.company, f"Excepción: {transfer.code} tiene diferencias.", transfer)
    else:
        notify_managers(transfer.origin, f"{transfer.code} fue recibido correctamente.", transfer)
    audit(user=user, action="RECEIVE", instance=transfer, description=f"{user} confirmó la recepción.", request=request)
    notify_commercial_reconcilers(transfer.company, f"{transfer.code} está pendiente de conciliación comercial.", transfer)
    queue_transfer_received_emails(transfer)
    return transfer


@transaction.atomic
def resolve_incident(incident, user, resolution_type, resolution_text, request=None):
    incident = Incident.objects.select_for_update().select_related("transfer").get(pk=incident.pk)
    transfer = incident.transfer
    if not user.is_operational or user.company_id != transfer.company_id or user.branch_id not in {transfer.origin_id, transfer.destination_id}:
        raise PermissionDenied
    if not user.has_capability("resolve_incident"):
        raise PermissionDenied
    if incident.status == Incident.Status.RESOLVED:
        raise ValidationError("La incidencia ya fue resuelta.")
    if not resolution_type or not resolution_text.strip():
        raise ValidationError("Selecciona el tipo y explica la resolución.")
    incident.status = Incident.Status.RESOLVED
    incident.resolution_type = resolution_type
    incident.resolution_text = resolution_text
    incident.resolved_by = user
    incident.resolved_at = timezone.now()
    incident.save(update_fields=("status", "resolution_type", "resolution_text", "resolved_by", "resolved_at", "updated_at"))
    audit(user=user, action="RESOLVE_INCIDENT", instance=incident, description=f"{incident.code} fue resuelta.", request=request)
    return incident


@transaction.atomic
def close_transfer(transfer, user, request=None):
    transfer = _lock_transfer(transfer)
    if not user.is_operational or user.company_id != transfer.company_id or user.branch_id not in {transfer.origin_id, transfer.destination_id}:
        raise PermissionDenied
    if not user.has_capability("close"):
        raise PermissionDenied
    if transfer.status not in {Transfer.Status.RECEIVED, Transfer.Status.RECEIVED_DIFFERENCES}:
        raise ValidationError("Solo puede cerrarse un traspaso recibido.")
    if hasattr(transfer, "incident") and transfer.incident.status != Incident.Status.RESOLVED:
        raise ValidationError("Resuelve la incidencia antes de cerrar.")
    transfer.status = Transfer.Status.CLOSED
    transfer.closed_by = user
    transfer.closed_at = timezone.now()
    transfer.save(update_fields=("status", "closed_by", "closed_at", "updated_at"))
    audit(user=user, action="CLOSE", instance=transfer, description=f"{user} cerró el traspaso.", request=request)
    return transfer


@transaction.atomic
def cancel_transfer(transfer, user, reason, request=None):
    transfer = _lock_transfer(transfer)
    if not user.is_operational or user.company_id != transfer.company_id or user.branch_id not in {transfer.origin_id, transfer.destination_id}:
        raise PermissionDenied
    if not user.has_capability("cancel"):
        raise PermissionDenied
    if transfer.status in {Transfer.Status.CLOSED, Transfer.Status.CANCELLED}:
        raise ValidationError("Este traspaso ya no puede anularse.")
    if not reason.strip():
        raise ValidationError("Debes indicar el motivo de la anulación.")
    transfer.status = Transfer.Status.CANCELLED
    transfer.cancelled_by = user
    transfer.cancelled_at = timezone.now()
    transfer.cancellation_reason = reason
    transfer.save(update_fields=("status", "cancelled_by", "cancelled_at", "cancellation_reason", "updated_at"))
    audit(user=user, action="CANCEL", instance=transfer, description=f"{user} anuló el traspaso.", request=request, reason=reason)
    notify_managers(transfer.origin, f"{transfer.code} fue anulado.", transfer)
    notify_managers(transfer.destination, f"{transfer.code} fue anulado.", transfer)
    notify_company_admins(transfer.company, f"Excepción: {transfer.code} fue anulado.", transfer)
    return transfer


@transaction.atomic
def save_commercial_registration(transfer, user, data, reason="", request=None):
    transfer = _lock_transfer(transfer)
    if not user.is_commercial_reconciler or user.company_id != transfer.company_id:
        raise PermissionDenied
    if transfer.status not in {Transfer.Status.RECEIVED, Transfer.Status.RECEIVED_DIFFERENCES, Transfer.Status.CLOSED}:
        raise ValidationError("El traspaso debe haber sido recibido.")
    registration = CommercialRegistration.objects.filter(transfer=transfer).first()
    before = snapshot(registration) if registration else None
    if registration and not reason.strip():
        raise ValidationError("Indica el motivo de la corrección.")
    if registration:
        registration.external_reference = data["external_reference"]
        registration.external_date = data["external_date"]
        registration.notes = data.get("notes", "")
        registration.registered_by = user
        registration.save()
        action = "CORRECT_COMMERCIAL"
    else:
        registration = CommercialRegistration.objects.create(transfer=transfer, registered_by=user, **data)
        action = "REGISTER_COMMERCIAL"
    audit(
        user=user,
        action=action,
        instance=transfer,
        description=f"Se registró la referencia comercial {registration.external_reference}.",
        request=request,
        before=before,
        after=snapshot(registration),
        reason=reason,
    )
    if action == "REGISTER_COMMERCIAL":
        queue_transfer_reconciled_emails(transfer, registration)
    return registration
