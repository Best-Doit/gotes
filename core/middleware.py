from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin
from datetime import timedelta
import logging

from .models import LoginThrottle


logger = logging.getLogger(__name__)


class LoginThrottleMiddleware(MiddlewareMixin):
    """Shared, atomic request budget for both login endpoints; no forwarded IP trust."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or request.resolver_match.url_name != "login":
            return None
        now = timezone.now()
        seconds = settings.LOGIN_RATE_WINDOW_SECONDS
        key = salted_hmac("gotes.login.ip", request.META.get("REMOTE_ADDR", "unknown"), algorithm="sha256").hexdigest()
        bucket, created = LoginThrottle.objects.get_or_create(key=key)
        if created:
            LoginThrottle.objects.filter(window_started__lt=now - timedelta(days=1)).delete()
        LoginThrottle.objects.filter(key=key, window_started__lte=now - timedelta(seconds=seconds)).update(
            attempts=0, window_started=now,
        )
        admitted = LoginThrottle.objects.filter(key=key, attempts__lt=settings.LOGIN_RATE_MAX_ATTEMPTS).update(
            attempts=F("attempts") + 1,
        )
        if not admitted:
            logger.warning("Límite de inicio de sesión alcanzado.")
            response = HttpResponse("Demasiados intentos. Espera unos minutos e inténtalo nuevamente.", status=429)
            response["Retry-After"] = str(seconds)
            return response
        return None


class SuspendedSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # The authentication backend rejects suspended users on every request.
        # Remove the old session so reactivation cannot revive it.
        if SESSION_KEY in request.session and not request.user.is_authenticated:
            request.session.flush()
        return self.get_response(request)


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
