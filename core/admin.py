from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm

from .models import (
    AuditLog,
    Branch,
    CommercialRegistration,
    Company,
    EmailOutbox,
    Evidence,
    Incident,
    IncidentDifference,
    Notification,
    Product,
    Receipt,
    ReceiptItem,
    Sequence,
    Transfer,
    TransferItem,
    User,
)
from .services import audit, snapshot


class SuperAdminSite(admin.AdminSite):
    site_header = "GOTES — Administración técnica y correcciones"
    site_title = "GOTES Admin"
    index_title = "Empresas, administradores y soporte excepcional"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


superadmin_site = SuperAdminSite(name="superadmin")


class AuditedUserChangeForm(UserChangeForm):
    correction_reason = forms.CharField(
        label="Motivo de la corrección",
        required=True,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Obligatorio: se guardará junto con los valores anteriores y posteriores.",
    )

    class Meta(UserChangeForm.Meta):
        model = User


class CompanyAdminCreationForm(AdminUserCreationForm):
    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "company", "first_name", "last_name", "email", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["company"].required = True
        self.instance.role = User.Role.COMPANY_ADMIN
        self.instance.branch = None
        self.instance.is_staff = False
        self.instance.is_superuser = False

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.COMPANY_ADMIN
        user.branch = None
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class ReasonedAdminForm(forms.ModelForm):
    correction_reason = forms.CharField(
        label="Motivo de la corrección",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Obligatorio al modificar un registro existente.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.instance._allow_historical_correction = True

    def clean(self):
        cleaned = super().clean()
        changes = [field for field in self.changed_data if field != "correction_reason"]
        if self.instance.pk and changes and not cleaned.get("correction_reason", "").strip():
            self.add_error("correction_reason", "Indica por qué se realiza esta corrección.")
        return cleaned


class AuditedAdmin(admin.ModelAdmin):
    form = ReasonedAdminForm

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            before = snapshot(type(obj).objects.get(pk=obj.pk))
        super().save_model(request, obj, form, change)
        audit(
            user=request.user,
            action="SUPERADMIN_UPDATE" if change else "SUPERADMIN_CREATE",
            instance=obj,
            description=f"Superadmin {'corrigió' if change else 'creó'} {obj._meta.verbose_name}: {obj}.",
            request=request,
            before=before,
            after=snapshot(obj),
            reason=form.cleaned_data.get("correction_reason", ""),
        )

    def delete_model(self, request, obj):
        raise PermissionError("Los registros operativos no se eliminan.")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Company, site=superadmin_site)
class CompanyAdmin(AuditedAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser


@admin.register(Branch, site=superadmin_site)
class BranchAdmin(AuditedAdmin):
    list_display = ("code", "name", "company", "is_active")
    list_filter = ("company", "is_active")
    search_fields = ("code", "name")


@admin.register(User, site=superadmin_site)
class UserAdmin(DjangoUserAdmin):
    form = AuditedUserChangeForm
    add_form = CompanyAdminCreationForm
    fieldsets = DjangoUserAdmin.fieldsets + (("Alcance GOTES", {"fields": (
        "role", "company", "branch", "phone", "allow_dispatch", "allow_close", "allow_cancel", "allow_resolve_incident",
    )}), ("Auditoría", {"fields": ("correction_reason",)}))
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "usable_password", "password1", "password2")}),
        ("Administrador de empresa", {
            "description": "Django Admin solo crea administradores. Las demás cuentas se crean en Usuarios y reciben rol y sucursal desde Asignaciones.",
            "fields": ("company", "first_name", "last_name", "email", "is_active"),
        }),
    )
    list_display = ("username", "role", "company", "branch", "is_active", "is_superuser")
    list_filter = ("role", "company", "is_active")

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def save_model(self, request, obj, form, change):
        before = snapshot(User.objects.get(pk=obj.pk)) if change else None
        super().save_model(request, obj, form, change)
        audit(
            user=request.user,
            action="SUPERADMIN_UPDATE" if change else "SUPERADMIN_CREATE",
            instance=obj,
            description=f"Superadmin {'corrigió' if change else 'creó'} el usuario {obj.username}.",
            request=request,
            before=before,
            after=snapshot(obj),
            reason=form.cleaned_data.get("correction_reason", ""),
        )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Product, site=superadmin_site)
class ProductAdmin(AuditedAdmin):
    list_display = ("code", "name", "category", "company")
    list_filter = ("company", "category")
    search_fields = ("code", "name", "category")


@admin.register(Transfer, site=superadmin_site)
class TransferAdmin(AuditedAdmin):
    list_display = ("code", "company", "origin", "destination", "status", "created_at")
    list_filter = ("company", "status")
    search_fields = ("code",)
    readonly_fields = ("uuid", "year", "sequence", "code", "created_at", "updated_at")


@admin.register(TransferItem, site=superadmin_site)
class TransferItemAdmin(AuditedAdmin):
    list_display = ("transfer", "product", "quantity_sent")
    search_fields = ("transfer__code", "product__name", "product__code")


@admin.register(Receipt, site=superadmin_site)
class ReceiptAdmin(AuditedAdmin):
    list_display = ("transfer", "status", "started_by", "confirmed_by", "confirmed_at")


@admin.register(ReceiptItem, site=superadmin_site)
class ReceiptItemAdmin(AuditedAdmin):
    list_display = ("receipt", "product", "quantity_received", "is_unexpected", "is_damaged")


@admin.register(Evidence, site=superadmin_site)
class EvidenceAdmin(AuditedAdmin):
    list_display = ("transfer", "type", "original_name", "uploaded_by", "objected")
    list_filter = ("type", "objected", "transfer__company")
    readonly_fields = ("uuid", "original_name", "created_at", "updated_at")

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj:
            fields.extend(("transfer", "type", "file", "uploaded_by", "correction_of"))
        return fields


@admin.register(Incident, site=superadmin_site)
class IncidentAdmin(AuditedAdmin):
    list_display = ("code", "company", "transfer", "status", "created_at")
    list_filter = ("company", "status")
    readonly_fields = ("year", "sequence", "code", "created_at", "updated_at")


@admin.register(IncidentDifference, site=superadmin_site)
class IncidentDifferenceAdmin(AuditedAdmin):
    list_display = ("incident", "product", "type", "quantity_sent", "quantity_received")


@admin.register(CommercialRegistration, site=superadmin_site)
class CommercialRegistrationAdmin(AuditedAdmin):
    list_display = ("transfer", "external_reference", "external_date", "registered_by")


@admin.register(Notification, site=superadmin_site)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "message", "is_read", "created_at")
    readonly_fields = ("user", "transfer", "message", "is_read", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailOutbox, site=superadmin_site)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event", "recipient_email", "status", "attempts", "sent_at")
    list_filter = ("event", "status")
    search_fields = ("recipient_email", "subject", "transfer__code")
    readonly_fields = tuple(field.name for field in EmailOutbox._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog, site=superadmin_site)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "object_type", "object_uuid", "company")
    list_filter = ("action", "company")
    search_fields = ("object_uuid", "description", "reason")
    readonly_fields = tuple(field.name for field in AuditLog._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Sequence, site=superadmin_site)
class SequenceAdmin(admin.ModelAdmin):
    list_display = ("company", "kind", "year", "next_value")
    readonly_fields = ("company", "kind", "year", "next_value")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
