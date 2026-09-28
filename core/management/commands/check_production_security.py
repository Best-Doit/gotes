from django.core.checks import WARNING, run_checks
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Impide arrancar producción con advertencias de seguridad obligatorias."

    def handle(self, *args, **options):
        # Subdomain coverage and browser preloading require an explicit domain policy.
        optional_hsts = {"security.W005", "security.W021"}
        issues = run_checks(include_deployment_checks=True)
        blocking = [issue for issue in issues if issue.level >= WARNING and issue.id not in optional_hsts]
        if blocking:
            raise CommandError("\n".join(str(issue) for issue in blocking))
        self.stdout.write(self.style.SUCCESS("Configuración de producción verificada."))
