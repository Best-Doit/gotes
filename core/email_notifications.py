import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .models import EmailOutbox, Transfer, User


logger = logging.getLogger(__name__)


def _transfer_url(transfer):
    path = reverse("transfer_detail", kwargs={"uuid": transfer.uuid})
    base_url = settings.GOTES_PUBLIC_URL.rstrip("/")
    return f"{base_url}{path}" if base_url else path


def _involved_managers(transfer):
    return User.objects.filter(
        company=transfer.company,
        branch_id__in=(transfer.origin_id, transfer.destination_id),
        role=User.Role.MANAGER,
        is_active=True,
    ).exclude(email="").order_by("pk")


def _commercial_reconcilers(transfer):
    return User.objects.filter(
        company=transfer.company,
        role=User.Role.RECONCILER,
        is_active=True,
    ).exclude(email="").order_by("pk")


def _queue_for_users(transfer, event, subject, body_builder, recipients):
    deliveries = []
    for recipient in recipients:
        deliveries.append(EmailOutbox(
            transfer=transfer,
            recipient=recipient,
            recipient_email=recipient.email,
            event=event,
            subject=subject,
            body=body_builder(recipient),
        ))
    return EmailOutbox.objects.bulk_create(deliveries, ignore_conflicts=True)


def queue_transfer_dispatched_emails(transfer):
    subject = f"[GOTES] {transfer.code} fue despachado"
    transfer_url = _transfer_url(transfer)

    def body(recipient):
        name = recipient.get_full_name() or recipient.username
        return "\n".join((
            f"Hola {name},",
            "",
            "Se confirmó la salida de un traspaso entre sucursales.",
            f"Código: {transfer.code}",
            f"Origen: {transfer.origin.name}",
            f"Destino: {transfer.destination.name}",
            f"Productos: {transfer.items.count()} líneas",
            f"Confirmado por: {transfer.dispatched_by or transfer.created_by}",
            "",
            f"Abrir seguimiento: {transfer_url}",
            "",
            "Este correo fue generado automáticamente por GOTES.",
        ))

    recipients = list(_involved_managers(transfer)) + list(_commercial_reconcilers(transfer))
    return _queue_for_users(transfer, EmailOutbox.Event.TRANSFER_DISPATCHED, subject, body, recipients)


def queue_transfer_received_emails(transfer):
    subject = f"[GOTES] {transfer.code} fue recepcionado"
    transfer_url = _transfer_url(transfer)
    result = "Recibido con diferencias" if transfer.status == Transfer.Status.RECEIVED_DIFFERENCES else "Recibido conforme"

    def body(recipient):
        name = recipient.get_full_name() or recipient.username
        is_reconciler = recipient.role == User.Role.RECONCILER
        return "\n".join((
            f"Hola {name},",
            "",
            (
                "La recepción fue confirmada y el traspaso requiere conciliación comercial."
                if is_reconciler
                else "La recepción del traspaso fue confirmada."
            ),
            f"Código: {transfer.code}",
            f"Origen: {transfer.origin.name}",
            f"Destino: {transfer.destination.name}",
            f"Resultado de recepción: {result}",
            "",
            f"{'Abrir conciliación' if is_reconciler else 'Abrir seguimiento'}: {transfer_url}",
            "",
            "Este correo fue generado automáticamente por GOTES.",
        ))

    recipients = list(_involved_managers(transfer)) + list(_commercial_reconcilers(transfer))
    return _queue_for_users(
        transfer,
        EmailOutbox.Event.TRANSFER_RECEIVED,
        subject,
        body,
        recipients,
    )


def queue_transfer_reconciled_emails(transfer, registration):
    subject = f"[GOTES] {transfer.code} fue conciliado"
    transfer_url = _transfer_url(transfer)

    def body(recipient):
        name = recipient.get_full_name() or recipient.username
        return "\n".join((
            f"Hola {name},",
            "",
            "La conciliación comercial del traspaso fue completada.",
            f"Código: {transfer.code}",
            f"Origen: {transfer.origin.name}",
            f"Destino: {transfer.destination.name}",
            f"Referencia comercial: {registration.external_reference}",
            f"Fecha comercial: {registration.external_date:%d/%m/%Y}",
            f"Registrado por: {registration.registered_by}",
            "",
            f"Abrir seguimiento: {transfer_url}",
            "",
            "Este correo fue generado automáticamente por GOTES.",
        ))

    return _queue_for_users(
        transfer,
        EmailOutbox.Event.TRANSFER_RECONCILED,
        subject,
        body,
        _involved_managers(transfer),
    )


@transaction.atomic
def _claim_pending_deliveries(limit):
    stale_before = timezone.now() - timedelta(minutes=settings.EMAIL_OUTBOX_PROCESSING_TIMEOUT_MINUTES)
    EmailOutbox.objects.filter(
        status=EmailOutbox.Status.PROCESSING,
        updated_at__lt=stale_before,
        attempts__lt=settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
    ).update(status=EmailOutbox.Status.FAILED, last_error="El envío anterior quedó interrumpido; se reintentará.")

    deliveries = list(
        EmailOutbox.objects.select_for_update()
        .filter(
            Q(status=EmailOutbox.Status.PENDING) | Q(status=EmailOutbox.Status.FAILED),
            attempts__lt=settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
        )
        .order_by("created_at")[:limit]
    )
    for delivery in deliveries:
        delivery.status = EmailOutbox.Status.PROCESSING
        delivery.attempts += 1
        delivery.last_error = ""
        delivery.save(update_fields=("status", "attempts", "last_error", "updated_at"))
    return [delivery.pk for delivery in deliveries]


def send_pending_email_notifications(limit=50):
    summary = {"claimed": 0, "sent": 0, "failed": 0}
    delivery_ids = _claim_pending_deliveries(limit)
    summary["claimed"] = len(delivery_ids)

    for delivery_id in delivery_ids:
        delivery = EmailOutbox.objects.get(pk=delivery_id)
        try:
            EmailMessage(
                subject=delivery.subject,
                body=delivery.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=(delivery.recipient_email,),
            ).send(fail_silently=False)
        except Exception as error:
            logger.exception("No se pudo enviar el correo %s de la bandeja de salida.", delivery.pk)
            delivery.status = EmailOutbox.Status.FAILED
            delivery.last_error = str(error)[:2000]
            delivery.save(update_fields=("status", "last_error", "updated_at"))
            summary["failed"] += 1
        else:
            delivery.status = EmailOutbox.Status.SENT
            delivery.sent_at = timezone.now()
            delivery.last_error = ""
            delivery.save(update_fields=("status", "sent_at", "last_error", "updated_at"))
            summary["sent"] += 1
    return summary
