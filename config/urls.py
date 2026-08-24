from django.urls import include, path

from core.admin import superadmin_site


urlpatterns = [
    path("django-admin/", superadmin_site.urls),
    path("", include("core.urls")),
]
