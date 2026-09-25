import logging
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from .services import audit


@receiver(user_login_failed)
def log_login_failure(sender, credentials, request, **kwargs):
    # Never log submitted credentials or usernames.
    logging.getLogger(__name__).warning("Intento de autenticación fallido.")


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    audit(user=user, action="LOGIN", instance=user, description=f"{user.username} inició sesión.", request=request)


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    if user and user.is_authenticated:
        audit(user=user, action="LOGOUT", instance=user, description=f"{user.username} cerró sesión.", request=request)
