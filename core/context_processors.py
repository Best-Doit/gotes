from .models import Product


def navigation(request):
    if not request.user.is_authenticated:
        return {}
    route = request.resolver_match.url_name if request.resolver_match else ""
    headings = {
        "dashboard": ("Panel de control", "Centro de operaciones"),
        "transfer_list": ("Traspasos", "Operación y seguimiento"),
        "transfer_create": ("Nuevo traspaso", "Preparación de movimiento"),
        "transfer_detail": ("Detalle de traspaso", "Seguimiento operativo"),
        "transfer_edit": ("Editar traspaso", "Borrador operativo"),
        "receipt_edit": ("Recepción", "Verificación física"),
        "reports": ("Reportes", "Indicadores operativos"),
        "notifications": ("Avisos", "Centro de notificaciones"),
        "audit_list": ("Auditoría", "Historial inmutable"),
        "manage_branches": ("Sucursales", "Administración empresarial"),
        "manage_branch_edit": ("Editar sucursal", "Administración empresarial"),
        "manage_products": ("Productos", "Catálogo empresarial"),
        "manage_product_edit": ("Editar producto", "Catálogo empresarial"),
        "product_import": ("Importar productos", "Carga desde Excel"),
        "product_import_template": ("Plantilla de productos", "Carga desde Excel"),
        "manage_users": ("Usuarios", "Cuentas de acceso"),
        "manage_user_edit": ("Editar usuario", "Cuentas de acceso"),
        "manage_assignments": ("Asignaciones", "Usuarios, roles y sucursales"),
        "manage_assignment_edit": ("Editar asignación", "Usuarios, roles y sucursales"),
        "password_change": ("Mi cuenta", "Seguridad de acceso"),
    }
    page_heading, page_eyebrow = headings.get(route, ("Panel operativo", "GOTES"))
    products = Product.objects.all() if request.user.is_superuser else Product.objects.filter(company_id=request.user.company_id)
    unread_notifications = request.user.notifications.filter(is_read=False).count()
    return {
        "unread_notifications": unread_notifications,
        "unread_notifications_label": "99+" if unread_notifications > 99 else str(unread_notifications),
        "page_heading": page_heading,
        "page_eyebrow": page_eyebrow,
        "global_product_suggestions": products.order_by("name").values("code", "name")[:60],
    }
