import time

from django.core.management.base import BaseCommand
from django.db import OperationalError

from core.email_notifications import send_pending_email_notifications


class Command(BaseCommand):
    help = "Envía los correos pendientes de la bandeja de salida de GOTES."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=30)

    def handle(self, *args, **options):
        while True:
            try:
                summary = send_pending_email_notifications(limit=max(1, options["limit"]))
            except OperationalError as error:
                if not options["watch"]:
                    raise
                self.stderr.write(f"Bandeja de salida aún no disponible: {error}")
            else:
                if summary["claimed"]:
                    self.stdout.write(
                        f"Procesados: {summary['claimed']} · enviados: {summary['sent']} · fallidos: {summary['failed']}"
                    )
            if not options["watch"]:
                break
            time.sleep(max(5, options["interval"]))
