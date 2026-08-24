from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_allow_users_pending_assignment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("recipient_email", models.EmailField(max_length=254)),
                ("event", models.CharField(choices=[("TRANSFER_DISPATCHED", "Traspaso despachado"), ("TRANSFER_RECONCILED", "Traspaso conciliado")], max_length=40)),
                ("subject", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("status", models.CharField(choices=[("PENDING", "Pendiente"), ("PROCESSING", "En proceso"), ("SENT", "Enviado"), ("FAILED", "Fallido")], db_index=True, default="PENDING", max_length=20)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("recipient", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="email_deliveries", to=settings.AUTH_USER_MODEL)),
                ("transfer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_deliveries", to="core.transfer")),
            ],
            options={
                "verbose_name": "correo en bandeja de salida",
                "verbose_name_plural": "correos en bandeja de salida",
                "ordering": ("created_at",),
                "indexes": [models.Index(fields=["status", "created_at"], name="email_outbox_queue_idx")],
                "constraints": [models.UniqueConstraint(fields=("transfer", "event", "recipient_email"), name="unique_transfer_email_event_recipient")],
            },
        ),
    ]
