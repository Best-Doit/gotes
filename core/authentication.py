from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import User


def active_scope(user):
    """Read current suspension flags even when the caller holds a cached user."""
    if not user or not user.pk:
        return False
    return User.objects.filter(pk=user.pk, is_active=True).filter(
        Q(is_superuser=True)
        | (Q(company__is_active=True) & (Q(branch__isnull=True) | Q(branch__is_active=True)))
    ).exists()


def require_active_scope(user):
    if not active_scope(user):
        raise PermissionDenied("La cuenta, empresa o sucursal está inactiva.")


class TenantModelBackend(ModelBackend):
    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and active_scope(user)
