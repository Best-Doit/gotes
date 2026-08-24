from django.db import migrations


def rename_pending_email_brand(apps, schema_editor):
    EmailOutbox = apps.get_model("core", "EmailOutbox")
    pending_statuses = ("PENDING", "PROCESSING", "FAILED")
    for delivery in EmailOutbox.objects.filter(status__in=pending_statuses).iterator():
        subject = delivery.subject.replace("[GOTS]", "[GOTES]")
        body = delivery.body.replace("por GOTS.", "por GOTES.")
        if subject != delivery.subject or body != delivery.body:
            delivery.subject = subject
            delivery.body = body
            delivery.save(update_fields=("subject", "body"))


class Migration(migrations.Migration):

    dependencies = [("core", "0007_email_outbox")]

    operations = [migrations.RunPython(rename_pending_email_brand, migrations.RunPython.noop)]
