from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class SuperuserAdminOnlyMiddleware:
    """Keep technical superusers out of the business application."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        allowed_prefixes = ("/django-admin/", settings.STATIC_URL)
        if (
            user
            and user.is_authenticated
            and user.is_superuser
            and request.path != reverse("logout")
            and not request.path.startswith(allowed_prefixes)
        ):
            return redirect("superadmin:index")
        return self.get_response(request)
