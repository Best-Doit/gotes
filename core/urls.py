from django.contrib.auth import views as auth_views
from django.urls import path

from .forms import LoginForm
from . import views


urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html", authentication_form=LoginForm), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("traspasos/", views.transfer_list, name="transfer_list"),
    path("traspasos/exportar.csv", views.transfer_export_csv, name="transfer_export_csv"),
    path("traspasos/nuevo/", views.transfer_create, name="transfer_create"),
    path("traspasos/<uuid:uuid>/", views.transfer_detail, name="transfer_detail"),
    path("traspasos/<uuid:uuid>/editar/", views.transfer_edit, name="transfer_edit"),
    path("traspasos/<uuid:uuid>/evidencia/", views.upload_evidence, name="upload_evidence"),
    path("traspasos/<uuid:uuid>/preparar/", views.transfer_prepare, name="transfer_prepare"),
    path("traspasos/<uuid:uuid>/borrador/", views.transfer_return_draft, name="transfer_return_draft"),
    path("traspasos/<uuid:uuid>/despachar/", views.transfer_dispatch, name="transfer_dispatch"),
    path("traspasos/<uuid:uuid>/recibir/", views.receipt_edit, name="receipt_edit"),
    path("traspasos/<uuid:uuid>/confirmar-recepcion/", views.receipt_confirm, name="receipt_confirm"),
    path("traspasos/<uuid:uuid>/resolver-incidencia/", views.incident_resolve, name="incident_resolve"),
    path("traspasos/<uuid:uuid>/cerrar/", views.transfer_close, name="transfer_close"),
    path("traspasos/<uuid:uuid>/anular/", views.transfer_cancel, name="transfer_cancel"),
    path("traspasos/<uuid:uuid>/registro-comercial/", views.commercial_register, name="commercial_register"),
    path("evidencias/<uuid:uuid>/", views.evidence_download, name="evidence_download"),
    path("notificaciones/", views.notifications, name="notifications"),
    path("notificaciones/<int:pk>/abrir/", views.notification_open, name="notification_open"),
    path("auditoria/", views.audit_list, name="audit_list"),
    path("reportes/", views.reports, name="reports"),
    path("mi-cuenta/clave/", auth_views.PasswordChangeView.as_view(template_name="registration/password_change.html", success_url="/"), name="password_change"),
    path("empresa/sucursales/", views.manage_branches, name="manage_branches"),
    path("empresa/sucursales/<int:pk>/", views.manage_branches, name="manage_branch_edit"),
    path("empresa/productos/", views.manage_products, name="manage_products"),
    path("empresa/productos/importar/", views.product_import, name="product_import"),
    path("empresa/productos/plantilla.xlsx", views.product_import_template, name="product_import_template"),
    path("empresa/productos/<int:pk>/", views.manage_products, name="manage_product_edit"),
    path("empresa/usuarios/", views.manage_users, name="manage_users"),
    path("empresa/usuarios/<int:pk>/", views.manage_users, name="manage_user_edit"),
    path("empresa/asignaciones/", views.manage_assignments, name="manage_assignments"),
    path("empresa/asignaciones/<int:pk>/", views.manage_assignments, name="manage_assignment_edit"),
]
