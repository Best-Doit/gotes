from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone

from .models import (
    Branch,
    CommercialRegistration,
    Evidence,
    Incident,
    Product,
    Receipt,
    ReceiptItem,
    Transfer,
    TransferItem,
    User,
)
from .validators import validate_evidence_content_type


class StyledFormMixin:
    def _style_fields(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "checkbox checkbox-xs")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "select select-sm w-full")
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("class", "textarea textarea-sm w-full")
            elif isinstance(field.widget, forms.FileInput):
                field.widget.attrs.setdefault("class", "file-input file-input-sm w-full")
            else:
                field.widget.attrs.setdefault("class", "input input-sm w-full")


class LoginForm(StyledFormMixin, AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class TransferForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Transfer
        fields = ("destination", "notes")
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 1,
                    "class": "textarea textarea-sm h-8 min-h-8 w-full resize-none py-1.5",
                }
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destination"].queryset = Branch.objects.filter(company=user.company, is_active=True).exclude(pk=user.branch_id)
        self._style_fields()


class TransferItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TransferItem
        fields = ("product", "quantity_sent", "send_note")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=company)
        self._style_fields()
        self.fields["quantity_sent"].widget.attrs["class"] = "input input-sm w-full"
        self.fields["send_note"].widget.attrs["class"] = "input input-sm w-full"


TransferItemFormSet = inlineformset_factory(
    Transfer,
    TransferItem,
    form=TransferItemForm,
    fields=("product", "quantity_sent", "send_note"),
    extra=1,
    can_delete=True,
)


class EvidenceForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ("type", "file", "description")
        widgets = {"file": forms.FileInput(attrs={
            "accept": ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf",
            "capture": "environment",
        })}

    def __init__(self, *args, allowed_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        if allowed_types:
            self.fields["type"].choices = [(value, label) for value, label in Evidence.Type.choices if value in allowed_types]
        self.fields["file"].help_text = f"JPG, PNG, WEBP o PDF · máximo {settings.EVIDENCE_MAX_FILE_SIZE_MB} MB."
        self._style_fields()

    def clean_file(self):
        upload = self.cleaned_data["file"]
        validate_evidence_content_type(upload)
        return upload


class ExpectedReceiptItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReceiptItem
        fields = ("quantity_received", "is_damaged", "observation")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


ExpectedReceiptFormSet = modelformset_factory(
    ReceiptItem,
    form=ExpectedReceiptItemForm,
    extra=0,
)


class UnexpectedReceiptItemForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReceiptItem
        fields = ("product", "quantity_received", "is_damaged", "observation")

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(company=company)
        self.fields["quantity_received"].required = False
        self._style_fields()


UnexpectedReceiptFormSet = inlineformset_factory(
    parent_model=Receipt,
    model=ReceiptItem,
    form=UnexpectedReceiptItemForm,
    fields=("product", "quantity_received", "is_damaged", "observation"),
    extra=1,
    can_delete=True,
)


class IncidentResolutionForm(StyledFormMixin, forms.Form):
    resolution_type = forms.ChoiceField(label="Tipo de resolución", choices=Incident.ResolutionType.choices)
    resolution_text = forms.CharField(label="Explicación", widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class CommercialRegistrationForm(StyledFormMixin, forms.ModelForm):
    correction_reason = forms.CharField(label="Motivo de corrección", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = CommercialRegistration
        fields = ("external_reference", "external_date", "notes")
        widgets = {
            "external_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["external_reference"].label = "Referencia comercial"
        self.fields["external_reference"].widget.attrs.setdefault("placeholder", "Ej. SIS-TR-908")
        self.fields["external_date"].label = "Fecha"
        if not self.is_bound and not self.instance.pk:
            self.initial.setdefault("external_date", timezone.localdate())
        if self.instance.pk:
            self.fields["correction_reason"].required = True
        else:
            self.fields.pop("correction_reason")
        self._style_fields()


class BranchForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Branch
        fields = ("code", "name", "address", "phone", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class ProductForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ("code", "name", "category")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class ProductImportForm(StyledFormMixin, forms.Form):
    file = forms.FileField(
        label="Archivo Excel",
        help_text="Formato .xlsx, máximo 5 MB.",
        widget=forms.FileInput(attrs={"accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if not uploaded.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Selecciona un archivo Excel con extensión .xlsx.")
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("El archivo no puede superar 5 MB.")
        return uploaded


class TenantUserForm(StyledFormMixin, forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", required=False, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("username", "first_name", "email")

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        self.instance.company = company
        self.fields["first_name"].required = True
        self.fields["first_name"].label = "Nombre"
        self.fields["email"].help_text = "Opcional; se utilizará para futuras notificaciones por correo."
        if not self.instance.pk:
            self.fields["password1"].required = True
        self._style_fields()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.company = self.company
        if not user.pk:
            user.role = ""
            user.branch = None
            user.allow_dispatch = None
            user.allow_close = None
            user.allow_cancel = None
            user.allow_resolve_incident = None
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.full_clean()
            user.save()
        return user

    def clean_password1(self):
        password = self.cleaned_data.get("password1")
        if password:
            candidate = self.instance
            candidate.username = self.cleaned_data.get("username", candidate.username)
            validate_password(password, candidate)
        return password


class UserAssignmentForm(StyledFormMixin, forms.Form):
    user = forms.ModelChoiceField(label="Usuario", queryset=User.objects.none())
    role = forms.ChoiceField(label="Rol", choices=(
        ("", "Selecciona un rol"),
        (User.Role.MANAGER, "Encargado"),
        (User.Role.RECONCILER, "Conciliador comercial"),
        (User.Role.AUDITOR, "Auditor"),
    ))
    branch = forms.ModelChoiceField(label="Sucursal", queryset=Branch.objects.none(), required=False)

    def __init__(self, *args, company=None, assignment_user=None, **kwargs):
        self.company = company
        self.assignment_user = assignment_user
        super().__init__(*args, **kwargs)
        assignable_users = User.objects.filter(company=company).exclude(
            role__in=(User.Role.SUPERADMIN, User.Role.COMPANY_ADMIN),
        )
        if assignment_user:
            self.fields["user"].queryset = assignable_users.filter(pk=assignment_user.pk)
            self.fields["user"].initial = assignment_user
            self.fields["user"].disabled = True
            self.fields["role"].initial = assignment_user.role or None
            self.fields["branch"].initial = assignment_user.branch
        else:
            self.fields["user"].queryset = assignable_users.filter(role="").order_by("first_name", "username")
        self.fields["branch"].queryset = Branch.objects.filter(company=company, is_active=True)
        self.fields["branch"].help_text = "Solo es obligatoria para el rol Encargado."
        self._style_fields()

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        if role == User.Role.MANAGER and not cleaned.get("branch"):
            self.add_error("branch", "Selecciona la sucursal del encargado.")
        elif role in {User.Role.RECONCILER, User.Role.AUDITOR}:
            cleaned["branch"] = None
        return cleaned

    def save(self):
        user = self.cleaned_data["user"]
        user.role = self.cleaned_data["role"]
        user.branch = self.cleaned_data.get("branch")
        if user.role != User.Role.MANAGER:
            user.allow_dispatch = None
            user.allow_close = None
            user.allow_cancel = None
            user.allow_resolve_incident = None
        user.full_clean()
        user.save(update_fields=(
            "role", "branch", "allow_dispatch", "allow_close", "allow_cancel", "allow_resolve_incident",
        ))
        return user
