import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date

from .forms import (
    BranchForm,
    CommercialRegistrationForm,
    EvidenceForm,
    ExpectedReceiptFormSet,
    IncidentResolutionForm,
    ProductImportForm,
    ProductForm,
    TenantUserForm,
    TransferForm,
    TransferItemFormSet,
    UnexpectedReceiptFormSet,
    UserAssignmentForm,
)
from .models import AuditLog, Branch, Evidence, Incident, Notification, Product, ReceiptItem, Transfer, User
from .product_import import InvalidProductWorkbook, build_product_template, parse_product_workbook
from .services import (
    audit,
    cancel_transfer,
    close_transfer,
    confirm_receipt,
    dispatch_transfer,
    get_or_start_receipt,
    prepare_transfer,
    resolve_incident,
    return_to_draft,
    save_commercial_registration,
    snapshot,
    visible_transfers,
)


def _validation_message(error):
    if hasattr(error, "messages"):
        return " ".join(error.messages)
    return str(error)


def _transfer_flow_redirect(uuid, *, saved=False):
    """Return to the transfer table and keep the operational flow open."""
    query = "?flow=1&saved=1" if saved else "?flow=1"
    return redirect(f"{reverse('transfer_detail', kwargs={'uuid': uuid})}{query}")


def _company_management_access(request, pk):
    if request.user.is_company_admin and request.user.company_id:
        return False
    if request.user.is_auditor and request.user.company_id and request.method == "GET" and pk is None:
        return True
    raise PermissionDenied


def _filtered_transfers(request):
    queryset = visible_transfers(request.user)
    status = request.GET.get("status", "")
    origin = request.GET.get("origin", "")
    destination = request.GET.get("destination", "")
    product = request.GET.get("product", "")
    user = request.GET.get("user", "")
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    query = request.GET.get("q", "").strip()
    commercial = request.GET.get("commercial", "")
    if status:
        queryset = queryset.filter(status=status)
    if origin:
        queryset = queryset.filter(origin_id=origin)
    if destination:
        queryset = queryset.filter(destination_id=destination)
    if product:
        queryset = queryset.filter(items__product_id=product)
    if user:
        queryset = queryset.filter(Q(created_by_id=user) | Q(prepared_by_id=user) | Q(dispatched_by_id=user)).distinct()
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query) |
            Q(items__product__name__icontains=query) |
            Q(items__product__code__icontains=query)
        ).distinct()
    if commercial == "pending":
        queryset = queryset.filter(commercial_registration__isnull=True, status__in=(
            Transfer.Status.RECEIVED,
            Transfer.Status.RECEIVED_DIFFERENCES,
            Transfer.Status.CLOSED,
        ))
    elif commercial == "registered":
        queryset = queryset.filter(commercial_registration__isnull=False)
    if request.GET.get("queue") == "receive":
        queryset = queryset.filter(status__in=(Transfer.Status.DISPATCHED, Transfer.Status.RECEIVING))
    return queryset


@login_required
def dashboard(request):
    queryset = visible_transfers(request.user)
    status_counts = {
        status: queryset.filter(status=status).count()
        for status, _label in Transfer.Status.choices
    }
    cards = [
        ("Por preparar", status_counts[Transfer.Status.DRAFT], "status=DRAFT"),
        ("Por despachar", status_counts[Transfer.Status.PREPARED], "status=PREPARED"),
        ("Por recibir", status_counts[Transfer.Status.DISPATCHED] + status_counts[Transfer.Status.RECEIVING], "queue=receive"),
        ("Con diferencias", status_counts[Transfer.Status.RECEIVED_DIFFERENCES], "status=RECEIVED_DIFFERENCES"),
    ]
    workflow = [
        ("Borradores", status_counts[Transfer.Status.DRAFT]),
        ("Preparados", status_counts[Transfer.Status.PREPARED]),
        ("En tránsito", status_counts[Transfer.Status.DISPATCHED] + status_counts[Transfer.Status.RECEIVING]),
        ("Recibidos", status_counts[Transfer.Status.RECEIVED] + status_counts[Transfer.Status.RECEIVED_DIFFERENCES]),
        ("Cerrados", status_counts[Transfer.Status.CLOSED]),
    ]
    workflow_max = max((count for _label, count in workflow), default=0) or 1
    active_total = queryset.exclude(status=Transfer.Status.CANCELLED).count()
    closure_rate = round((status_counts[Transfer.Status.CLOSED] / active_total) * 100) if active_total else 0
    commercial_eligible = queryset.filter(status__in=(
        Transfer.Status.RECEIVED,
        Transfer.Status.RECEIVED_DIFFERENCES,
        Transfer.Status.CLOSED,
    ))
    commercial_total = commercial_eligible.count()
    commercial_registered = commercial_eligible.filter(commercial_registration__isnull=False).count()
    commercial_rate = round((commercial_registered / commercial_total) * 100) if commercial_total else 0
    pending_commercial = commercial_total - commercial_registered
    onboarding = None
    if request.user.is_company_admin:
        onboarding = {
            "branches": Branch.objects.filter(company=request.user.company, is_active=True).count(),
            "products": Product.objects.filter(company=request.user.company).count(),
            "managers": User.objects.filter(company=request.user.company, role=User.Role.MANAGER, is_active=True).count(),
        }
        onboarding["ready"] = onboarding["branches"] >= 2 and onboarding["products"] > 0 and onboarding["managers"] >= 2
    return render(request, "core/dashboard.html", {
        "page_heading": "Panel de control",
        "page_eyebrow": "Centro de operaciones",
        "cards": cards,
        "recent": queryset[:10],
        "pending_receipts": queryset.filter(status__in=(Transfer.Status.DISPATCHED, Transfer.Status.RECEIVING))[:5],
        "workflow": workflow,
        "workflow_max": workflow_max,
        "closure_rate": closure_rate,
        "commercial_rate": commercial_rate,
        "commercial_total": commercial_total,
        "commercial_registered": commercial_registered,
        "pending_commercial": pending_commercial,
        "onboarding": onboarding,
    })


@login_required
def transfer_list(request):
    queryset = _filtered_transfers(request)
    if request.user.is_superuser:
        branches = Branch.objects.all()
        users = User.objects.filter(is_active=True)
    else:
        branches = Branch.objects.filter(company=request.user.company, is_active=True)
        users = User.objects.filter(company=request.user.company, is_active=True)
    active_filter_count = sum(
        bool(request.GET.get(key))
        for key in ("q", "status", "origin", "destination", "product", "user", "date_from", "date_to", "commercial", "queue")
    )
    page_obj = Paginator(queryset, 30).get_page(request.GET.get("page"))
    return render(request, "core/transfer_list.html", {
        "transfers": page_obj.object_list,
        "page_obj": page_obj,
        "statuses": Transfer.Status.choices,
        "branches": branches,
        "users": users,
        "active_filter_count": active_filter_count,
    })


@login_required
def transfer_export_csv(request):
    queryset = _filtered_transfers(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="traspasos.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(("Código", "Estado", "Origen", "Destino", "Creado", "Recibido", "Referencia comercial"))
    for transfer in queryset.select_related("origin", "destination"):
        registration = getattr(transfer, "commercial_registration", None)
        writer.writerow((
            transfer.code,
            transfer.get_status_display(),
            transfer.origin.name,
            transfer.destination.name,
            transfer.created_at.isoformat(),
            transfer.received_at.isoformat() if transfer.received_at else "",
            registration.external_reference if registration else "",
        ))
    return response


@login_required
def transfer_create(request):
    if not request.user.is_operational or not request.user.branch_id:
        raise PermissionDenied
    transfer = Transfer(company=request.user.company, origin=request.user.branch, created_by=request.user)
    if request.method == "POST":
        form = TransferForm(request.POST, instance=transfer, user=request.user)
        formset = TransferItemFormSet(request.POST, instance=transfer, form_kwargs={"company": request.user.company})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                transfer = form.save()
                items = formset.save(commit=False)
                for item in items:
                    item.transfer = transfer
                    item.full_clean()
                    item.save()
                for item in formset.deleted_objects:
                    if item.pk:
                        item.delete()
                audit(user=request.user, action="CREATE", instance=transfer, description=f"{request.user} creó el traspaso.", request=request)
            return _transfer_flow_redirect(transfer.uuid, saved=True)
    else:
        form = TransferForm(instance=transfer, user=request.user)
        formset = TransferItemFormSet(instance=transfer, form_kwargs={"company": request.user.company})
    return render(request, "core/transfer_form.html", {"form": form, "formset": formset, "title": "Nuevo traspaso", "page_heading": "Nuevo traspaso", "page_eyebrow": "Preparación de movimiento"})


@login_required
def transfer_edit(request, uuid):
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    if transfer.status != Transfer.Status.DRAFT or not request.user.is_operational or request.user.branch_id != transfer.origin_id:
        raise PermissionDenied
    if request.method == "POST":
        before = snapshot(transfer)
        form = TransferForm(request.POST, instance=transfer, user=request.user)
        formset = TransferItemFormSet(request.POST, instance=transfer, form_kwargs={"company": request.user.company})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                transfer = form.save()
                formset.save()
                audit(user=request.user, action="UPDATE", instance=transfer, description=f"{request.user} actualizó el borrador.", request=request, before=before, after=snapshot(transfer))
            return _transfer_flow_redirect(transfer.uuid, saved=True)
    else:
        form = TransferForm(instance=transfer, user=request.user)
        formset = TransferItemFormSet(instance=transfer, form_kwargs={"company": request.user.company})
    return render(request, "core/transfer_form.html", {"form": form, "formset": formset, "title": f"Editar {transfer.code}", "page_heading": f"Editar {transfer.code}", "page_eyebrow": "Borrador operativo"})


def _allowed_evidence_types(user, transfer):
    allowed = []
    if user.is_operational and user.branch_id == transfer.origin_id and transfer.status in {Transfer.Status.DRAFT, Transfer.Status.PREPARED}:
        allowed.extend((Evidence.Type.PREPARATION, Evidence.Type.DISPATCH))
    if user.is_operational and user.branch_id == transfer.destination_id and transfer.status in {Transfer.Status.DISPATCHED, Transfer.Status.RECEIVING}:
        allowed.append(Evidence.Type.RECEIPT)
    if user.is_operational and user.branch_id in {transfer.origin_id, transfer.destination_id} and transfer.status == Transfer.Status.RECEIVED_DIFFERENCES:
        allowed.append(Evidence.Type.INCIDENT)
    return allowed


@login_required
def transfer_detail(request, uuid):
    transfer = get_object_or_404(visible_transfers(request.user).prefetch_related("items__product", "evidences"), uuid=uuid)
    object_ids = [str(transfer.uuid), transfer.code]
    if hasattr(transfer, "incident"):
        object_ids.append(transfer.incident.code)
    timeline = AuditLog.objects.filter(company=transfer.company, object_uuid__in=object_ids).select_related("user")
    allowed_evidence_types = _allowed_evidence_types(request.user, transfer)
    preferred_evidence_type = None
    if Evidence.Type.DISPATCH in allowed_evidence_types and transfer.status == Transfer.Status.PREPARED:
        preferred_evidence_type = Evidence.Type.DISPATCH
    elif Evidence.Type.RECEIPT in allowed_evidence_types:
        preferred_evidence_type = Evidence.Type.RECEIPT
    elif allowed_evidence_types:
        preferred_evidence_type = allowed_evidence_types[0]
    evidence_form = EvidenceForm(
        allowed_types=allowed_evidence_types,
        initial={"type": preferred_evidence_type} if preferred_evidence_type else None,
    )
    has_dispatch_evidence = any(
        evidence.type == Evidence.Type.DISPATCH for evidence in transfer.evidences.all()
    )
    commercial_form = None
    if request.user.is_commercial_reconciler and transfer.status in {Transfer.Status.RECEIVED, Transfer.Status.RECEIVED_DIFFERENCES, Transfer.Status.CLOSED}:
        commercial_form = CommercialRegistrationForm(instance=getattr(transfer, "commercial_registration", None))
    resolution_form = None
    if hasattr(transfer, "incident") and transfer.incident.status != Incident.Status.RESOLVED:
        resolution_form = IncidentResolutionForm()
    return render(request, "core/transfer_detail.html", {
        "page_heading": transfer.code,
        "page_eyebrow": "Seguimiento operativo",
        "transfer": transfer,
        "timeline": timeline,
        "evidence_form": evidence_form,
        "allowed_evidence_types": allowed_evidence_types,
        "has_dispatch_evidence": has_dispatch_evidence,
        "can_dispatch_transfer": request.user.has_capability("dispatch"),
        "open_flow_modal": request.GET.get("flow") == "1",
        "draft_just_saved": request.GET.get("saved") == "1",
        "commercial_form": commercial_form,
        "is_commercial_correction": bool(commercial_form and commercial_form.instance.pk),
        "resolution_form": resolution_form,
    })


@login_required
def upload_evidence(request, uuid):
    if request.method != "POST":
        raise Http404
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    allowed = _allowed_evidence_types(request.user, transfer)
    form = EvidenceForm(request.POST, request.FILES, allowed_types=allowed)
    return_to_receipt = request.POST.get("_return_to") == "receipt" and Evidence.Type.RECEIPT in allowed
    evidence_saved = False
    if form.is_valid() and form.cleaned_data["type"] in allowed:
        evidence = form.save(commit=False)
        evidence.transfer = transfer
        evidence.uploaded_by = request.user
        evidence.full_clean()
        evidence.save()
        evidence_saved = True
        audit(user=request.user, action="ADD_EVIDENCE", instance=transfer, description=f"Se agregó evidencia de {evidence.get_type_display().lower()}.", request=request)
        if not return_to_receipt:
            messages.success(request, "Evidencia guardada.")
    else:
        if not return_to_receipt:
            messages.error(request, "No se pudo guardar la evidencia: " + " ".join(sum(form.errors.values(), [])))
    if return_to_receipt:
        step = 4 if evidence_saved else 3
        result = "evidence=1" if evidence_saved else "evidence_error=1"
        return redirect(f"{reverse('receipt_edit', kwargs={'uuid': transfer.uuid})}?flow=1&step={step}&{result}")
    return _transfer_flow_redirect(transfer.uuid)


@login_required
def evidence_download(request, uuid):
    evidence = get_object_or_404(Evidence.objects.select_related("transfer"), uuid=uuid)
    if not visible_transfers(request.user).filter(pk=evidence.transfer_id).exists():
        raise Http404
    try:
        return FileResponse(evidence.file.open("rb"), filename=evidence.original_name)
    except FileNotFoundError as exc:
        raise Http404 from exc


def _run_action(request, uuid, action, success_message, *, reason_field=None):
    if request.method != "POST":
        raise Http404
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    try:
        if reason_field:
            action(transfer, request.user, request.POST.get(reason_field, ""), request=request)
        else:
            action(transfer, request.user, request=request)
        messages.success(request, success_message)
    except ValidationError as error:
        messages.error(request, _validation_message(error))
    return _transfer_flow_redirect(uuid)


@login_required
def transfer_prepare(request, uuid):
    return _run_action(request, uuid, prepare_transfer, "Traspaso preparado.")


@login_required
def transfer_return_draft(request, uuid):
    return _run_action(request, uuid, return_to_draft, "El traspaso volvió a borrador.", reason_field="reason")


@login_required
def transfer_dispatch(request, uuid):
    return _run_action(request, uuid, dispatch_transfer, "Salida confirmada.")


@login_required
def transfer_close(request, uuid):
    return _run_action(request, uuid, close_transfer, "Traspaso cerrado.")


@login_required
def transfer_cancel(request, uuid):
    return _run_action(request, uuid, cancel_transfer, "Traspaso anulado.", reason_field="reason")


@login_required
def receipt_edit(request, uuid):
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    try:
        receipt = get_or_start_receipt(transfer, request.user, request=request)
    except ValidationError as error:
        messages.error(request, _validation_message(error))
        return _transfer_flow_redirect(uuid)
    if receipt.status != receipt.Status.DRAFT:
        return _transfer_flow_redirect(uuid)
    expected_queryset = ReceiptItem.objects.filter(receipt=receipt, is_unexpected=False).select_related("product", "transfer_item")
    unexpected_queryset = ReceiptItem.objects.filter(receipt=receipt, is_unexpected=True)
    if request.method == "POST":
        expected = ExpectedReceiptFormSet(request.POST, queryset=expected_queryset, prefix="expected")
        unexpected = UnexpectedReceiptFormSet(
            request.POST,
            instance=receipt,
            queryset=unexpected_queryset,
            prefix="unexpected",
            form_kwargs={"company": transfer.company},
        )
        expected_valid = expected.is_valid()
        unexpected_valid = unexpected.is_valid()
        if expected_valid and unexpected_valid:
            with transaction.atomic():
                expected.save()
                unexpected_items = unexpected.save(commit=False)
                for deleted in unexpected.deleted_objects:
                    deleted.delete()
                for item in unexpected_items:
                    item.receipt = receipt
                    item.transfer_item = None
                    item.is_unexpected = True
                    item.full_clean()
                    item.save()
                audit(user=request.user, action="SAVE_RECEIPT", instance=transfer, description=f"{request.user} guardó el borrador de recepción.", request=request)
            return redirect(f"{reverse('receipt_edit', kwargs={'uuid': uuid})}?flow=1&step=3&saved=1")
    else:
        expected = ExpectedReceiptFormSet(queryset=expected_queryset, prefix="expected")
        unexpected = UnexpectedReceiptFormSet(
            instance=receipt,
            queryset=unexpected_queryset,
            prefix="unexpected",
            form_kwargs={"company": transfer.company},
        )
    receipt_evidences = transfer.evidences.filter(type=Evidence.Type.RECEIPT)
    requested_step = request.GET.get("step", "1")
    try:
        initial_step = min(max(int(requested_step), 1), 4)
    except (TypeError, ValueError):
        initial_step = 1
    if request.method == "POST":
        initial_step = 1 if expected.errors else 2
    return render(request, "core/receipt_form.html", {
        "page_heading": f"Recibir {transfer.code}",
        "page_eyebrow": "Verificación física",
        "transfer": transfer,
        "receipt": receipt,
        "expected": expected,
        "unexpected": unexpected,
        "evidence_form": EvidenceForm(allowed_types=[Evidence.Type.RECEIPT], initial={"type": Evidence.Type.RECEIPT}),
        "receipt_evidences": receipt_evidences,
        "has_receipt_evidence": receipt_evidences.exists(),
        "initial_step": initial_step,
        "open_receipt_flow": request.GET.get("flow") == "1" or request.method == "POST",
        "draft_just_saved": request.GET.get("saved") == "1",
        "evidence_just_saved": request.GET.get("evidence") == "1",
        "evidence_error": request.GET.get("evidence_error") == "1",
        "confirm_error": request.GET.get("confirm_error") == "1",
    })


@login_required
def receipt_confirm(request, uuid):
    if request.method != "POST":
        raise Http404
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    try:
        confirm_receipt(transfer, request.user, request=request)
        messages.success(request, "Recepción confirmada.")
    except ValidationError:
        return redirect(f"{reverse('receipt_edit', kwargs={'uuid': uuid})}?flow=1&step=4&confirm_error=1")
    return _transfer_flow_redirect(uuid)


@login_required
def incident_resolve(request, uuid):
    if request.method != "POST":
        raise Http404
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    incident = get_object_or_404(Incident, transfer=transfer)
    form = IncidentResolutionForm(request.POST)
    if form.is_valid():
        try:
            resolve_incident(
                incident,
                request.user,
                form.cleaned_data["resolution_type"],
                form.cleaned_data["resolution_text"],
                request=request,
            )
            messages.success(request, "Incidencia resuelta.")
        except ValidationError as error:
            messages.error(request, _validation_message(error))
    return _transfer_flow_redirect(uuid)


@login_required
def commercial_register(request, uuid):
    if request.method != "POST":
        raise Http404
    transfer = get_object_or_404(visible_transfers(request.user), uuid=uuid)
    existing = getattr(transfer, "commercial_registration", None)
    form = CommercialRegistrationForm(request.POST, instance=existing)
    if form.is_valid():
        try:
            save_commercial_registration(
                transfer,
                request.user,
                {
                    "external_reference": form.cleaned_data["external_reference"],
                    "external_date": form.cleaned_data["external_date"],
                    "notes": form.cleaned_data["notes"],
                },
                reason=form.cleaned_data.get("correction_reason", ""),
                request=request,
            )
            messages.success(request, "Conciliación comercial guardada.")
        except ValidationError as error:
            messages.error(request, _validation_message(error))
    else:
        messages.error(request, "Revisa la referencia y la fecha comercial.")
    return _transfer_flow_redirect(uuid)


@login_required
def notifications(request):
    items = request.user.notifications.select_related("transfer")[:100]
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return redirect("notifications")
    return render(request, "core/notifications.html", {"notifications": items})


@login_required
def notification_open(request, pk):
    item = get_object_or_404(Notification, pk=pk, user=request.user)
    if not item.is_read:
        item.is_read = True
        item.save(update_fields=("is_read",))
    if item.transfer_id and visible_transfers(request.user).filter(pk=item.transfer_id).exists():
        return _transfer_flow_redirect(item.transfer.uuid)
    return redirect("notifications")


@login_required
def reports(request):
    queryset = visible_transfers(request.user)
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    status_counts = {row["status"]: row["total"] for row in queryset.values("status").annotate(total=Count("id"))}
    status_progress_classes = {
        Transfer.Status.DRAFT: "progress-neutral",
        Transfer.Status.PREPARED: "progress-info",
        Transfer.Status.DISPATCHED: "progress-primary",
        Transfer.Status.RECEIVING: "progress-warning",
        Transfer.Status.RECEIVED: "progress-success",
        Transfer.Status.RECEIVED_DIFFERENCES: "progress-error",
        Transfer.Status.CLOSED: "progress-success",
        Transfer.Status.CANCELLED: "progress-error",
    }
    statuses = [
        {
            "value": value,
            "label": label,
            "total": status_counts.get(value, 0),
            "progress_class": status_progress_classes[value],
        }
        for value, label in Transfer.Status.choices
    ]
    status_max = max((item["total"] for item in statuses), default=1) or 1
    flow_stages = [
        {
            "label": "Preparación",
            "description": "Borradores y preparados",
            "total": status_counts.get(Transfer.Status.DRAFT, 0) + status_counts.get(Transfer.Status.PREPARED, 0),
            "step_class": "step-neutral",
            "bar_class": "bg-neutral",
        },
        {
            "label": "En ruta",
            "description": "Despachados y en recepción",
            "total": status_counts.get(Transfer.Status.DISPATCHED, 0) + status_counts.get(Transfer.Status.RECEIVING, 0),
            "step_class": "step-info",
            "bar_class": "bg-info",
        },
        {
            "label": "Recepcionados",
            "description": "Conformes o con diferencias",
            "total": status_counts.get(Transfer.Status.RECEIVED, 0) + status_counts.get(Transfer.Status.RECEIVED_DIFFERENCES, 0),
            "step_class": "step-warning",
            "bar_class": "bg-warning",
        },
        {
            "label": "Cerrados",
            "description": "Proceso completado",
            "total": status_counts.get(Transfer.Status.CLOSED, 0),
            "step_class": "step-success",
            "bar_class": "bg-success",
        },
    ]
    active_total = sum(item["total"] for item in flow_stages)
    for stage in flow_stages:
        stage["percentage"] = round(stage["total"] * 100 / active_total) if active_total else 0
    received_statuses = (
        Transfer.Status.RECEIVED,
        Transfer.Status.RECEIVED_DIFFERENCES,
        Transfer.Status.CLOSED,
    )
    branch_rows = []
    branches = Branch.objects.filter(company=request.user.company, is_active=True)
    if not request.user.has_company_scope:
        branches = branches.filter(pk=request.user.branch_id)
    for branch in branches:
        sent = queryset.filter(origin=branch).count()
        incoming = queryset.filter(destination=branch).count()
        received = queryset.filter(destination=branch, status__in=received_statuses).count()
        differences = queryset.filter(destination=branch, incident__isnull=False).distinct().count()
        branch_rows.append({
            "branch": branch,
            "sent": sent,
            "incoming": incoming,
            "pending_receipt": max(incoming - received, 0),
            "received": received,
            "differences": differences,
            "closed": queryset.filter(Q(origin=branch) | Q(destination=branch), status=Transfer.Status.CLOSED).count(),
            "conformity_rate": round(max(received - differences, 0) * 100 / received) if received else 0,
        })

    branch_max = max(
        (max(row["sent"], row["incoming"], row["received"]) for row in branch_rows),
        default=1,
    ) or 1

    total = queryset.count()
    in_transit = queryset.filter(status__in=(Transfer.Status.DISPATCHED, Transfer.Status.RECEIVING)).count()
    received_total = queryset.filter(status__in=received_statuses).count()
    closed_total = queryset.filter(status=Transfer.Status.CLOSED).count()
    reconciled_total = queryset.filter(commercial_registration__isnull=False).count()
    conforming_total = queryset.filter(status__in=received_statuses, incident__isnull=True).count()
    pending_commercial = queryset.filter(
        commercial_registration__isnull=True,
        status__in=received_statuses,
    ).count()
    return render(request, "core/reports.html", {
        "statuses": statuses,
        "status_max": status_max,
        "flow_stages": flow_stages,
        "active_total": active_total,
        "branch_rows": branch_rows,
        "branch_max": branch_max,
        "total": total,
        "in_transit": in_transit,
        "received_total": received_total,
        "closed_total": closed_total,
        "closure_rate": round(closed_total * 100 / active_total) if active_total else 0,
        "reconciled_total": reconciled_total,
        "commercial_rate": round(reconciled_total * 100 / received_total) if received_total else 0,
        "conforming_total": conforming_total,
        "conformity_rate": round(conforming_total * 100 / received_total) if received_total else 0,
        "pending_commercial": pending_commercial,
        "cancelled_total": status_counts.get(Transfer.Status.CANCELLED, 0),
        "open_incidents": Incident.objects.filter(
            **({"company": request.user.company} if request.user.company_id else {}),
            status__in=(Incident.Status.OPEN, Incident.Status.IN_REVIEW),
            transfer__in=queryset,
        ).count(),
        "date_from": date_from.isoformat() if date_from else "",
        "date_to": date_to.isoformat() if date_to else "",
        "invalid_date_filter": bool(
            (request.GET.get("date_from") and not date_from) or
            (request.GET.get("date_to") and not date_to)
        ),
    })


@login_required
def audit_list(request):
    if request.user.is_superuser:
        logs = AuditLog.objects.all()
    elif request.user.has_company_scope:
        logs = AuditLog.objects.filter(company=request.user.company)
    elif request.user.is_operational:
        transfers = visible_transfers(request.user)[:500]
        object_ids = []
        for transfer in transfers:
            object_ids.extend((str(transfer.uuid), transfer.code))
            if hasattr(transfer, "incident"):
                object_ids.append(transfer.incident.code)
        logs = AuditLog.objects.filter(company=request.user.company).filter(Q(branch=request.user.branch) | Q(object_uuid__in=object_ids))
    else:
        raise PermissionDenied
    query = request.GET.get("q", "").strip()
    if query:
        logs = logs.filter(Q(description__icontains=query) | Q(object_uuid__icontains=query) | Q(action__icontains=query))
    return render(request, "core/audit_list.html", {"logs": logs.select_related("user", "branch")[:250]})


@login_required
def manage_branches(request, pk=None):
    read_only = _company_management_access(request, pk)
    instance = get_object_or_404(Branch, pk=pk, company=request.user.company) if pk else None
    form = BranchForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.company = request.user.company
        item.full_clean()
        item.save()
        audit(user=request.user, action="MANAGE_BRANCH", instance=item, description=f"Se guardó la sucursal {item}.", request=request)
        messages.success(request, "Sucursal guardada.")
        return redirect("manage_branches")
    return render(request, "core/manage.html", {
        "title": "Sucursales", "page_heading": "Sucursales", "page_eyebrow": "Administración empresarial", "form": form, "items": Branch.objects.filter(company=request.user.company), "edit_url_name": "manage_branch_edit", "read_only": read_only,
    })


@login_required
def manage_products(request, pk=None):
    read_only = _company_management_access(request, pk)
    instance = get_object_or_404(Product, pk=pk, company=request.user.company) if pk else None
    form = ProductForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.company = request.user.company
        item.full_clean()
        item.save()
        audit(user=request.user, action="MANAGE_PRODUCT", instance=item, description=f"Se guardó el producto {item}.", request=request)
        messages.success(request, "Producto guardado.")
        return redirect("manage_products")
    return render(request, "core/manage.html", {
        "title": "Productos", "page_heading": "Productos", "page_eyebrow": "Catálogo empresarial", "form": form, "import_form": ProductImportForm(), "items": Product.objects.filter(company=request.user.company), "edit_url_name": "manage_product_edit", "read_only": read_only,
    })


@login_required
def product_import_template(request):
    if not request.user.is_company_admin or not request.user.company_id:
        raise PermissionDenied
    return FileResponse(
        build_product_template(),
        as_attachment=True,
        filename="plantilla_productos_gotes.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@login_required
def product_import(request):
    if not request.user.is_company_admin or not request.user.company_id:
        raise PermissionDenied
    import_form = ProductImportForm(request.POST or None, request.FILES or None)
    import_errors = []
    errors_truncated = False
    if request.method == "POST" and import_form.is_valid():
        try:
            rows, import_errors, errors_truncated = parse_product_workbook(import_form.cleaned_data["file"])
        except InvalidProductWorkbook as error:
            import_form.add_error("file", str(error))
        else:
            if not import_errors:
                created_count = 0
                updated_count = 0
                current_line = 0
                try:
                    with transaction.atomic():
                        for row in rows:
                            current_line = row["line"]
                            item = Product.objects.filter(
                                company=request.user.company,
                                code=row["code"],
                            ).first()
                            before = snapshot(item) if item else None
                            if item:
                                item.name = row["name"]
                                item.category = row["category"]
                                item.full_clean()
                                item.save(update_fields=("name", "category", "updated_at"))
                                updated_count += 1
                                operation = "actualizó"
                            else:
                                item = Product(
                                    company=request.user.company,
                                    code=row["code"],
                                    name=row["name"],
                                    category=row["category"],
                                )
                                item.full_clean()
                                item.save()
                                created_count += 1
                                operation = "creó"
                            audit(
                                user=request.user,
                                action="IMPORT_PRODUCT",
                                instance=item,
                                description=f"La importación Excel {operation} el producto {item.code} desde la fila {current_line}.",
                                request=request,
                                before=before,
                                after=snapshot(item),
                            )
                except (ValidationError, IntegrityError) as error:
                    import_errors = [{
                        "line": current_line or "—",
                        "message": _validation_message(error),
                    }]
                else:
                    messages.success(
                        request,
                        f"Importación completada: {created_count} productos creados y {updated_count} actualizados.",
                    )
                    return redirect("manage_products")
    return render(request, "core/manage.html", {
        "title": "Productos",
        "page_heading": "Productos",
        "page_eyebrow": "Catálogo empresarial",
        "form": ProductForm(),
        "import_form": import_form,
        "items": Product.objects.filter(company=request.user.company),
        "edit_url_name": "manage_product_edit",
        "read_only": False,
        "import_errors": import_errors,
        "errors_truncated": errors_truncated,
        "show_import_modal": True,
    })


@login_required
def manage_users(request, pk=None):
    read_only = _company_management_access(request, pk)
    editable_queryset = User.objects.filter(company=request.user.company).exclude(
        role__in=(User.Role.SUPERADMIN, User.Role.COMPANY_ADMIN),
    )
    instance = get_object_or_404(editable_queryset, pk=pk) if pk else None
    form = TenantUserForm(request.POST or None, instance=instance, company=request.user.company)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        audit(user=request.user, action="MANAGE_USER", instance=item, description=f"Se guardó el usuario {item.username}.", request=request)
        messages.success(request, "Usuario guardado.")
        return redirect("manage_users")
    return render(request, "core/manage.html", {
        "title": "Usuarios", "page_heading": "Usuarios", "page_eyebrow": "Cuentas de acceso", "form": form, "items": User.objects.filter(company=request.user.company).select_related("branch"), "edit_url_name": "manage_user_edit", "read_only": read_only,
    })


@login_required
def manage_assignments(request, pk=None):
    read_only = _company_management_access(request, pk)
    assignable_users = User.objects.filter(company=request.user.company).exclude(
        role__in=(User.Role.SUPERADMIN, User.Role.COMPANY_ADMIN),
    )
    assignment_user = get_object_or_404(assignable_users, pk=pk) if pk else None
    form = UserAssignmentForm(
        request.POST or None,
        company=request.user.company,
        assignment_user=assignment_user,
    )
    if request.method == "POST" and form.is_valid():
        before = snapshot(form.cleaned_data["user"])
        item = form.save()
        audit(
            user=request.user,
            action="MANAGE_ASSIGNMENT",
            instance=item,
            description=f"Se asignó a {item.username} el rol {item.get_role_display()}.",
            request=request,
            before=before,
            after=snapshot(item),
        )
        messages.success(request, "Asignación guardada.")
        return redirect("manage_assignments")
    return render(request, "core/manage_assignments.html", {
        "form": form,
        "items": assignable_users.select_related("branch").order_by("first_name", "username"),
        "assignment_user": assignment_user,
        "read_only": read_only,
        "page_heading": "Asignaciones",
        "page_eyebrow": "Usuarios, roles y sucursales",
    })
