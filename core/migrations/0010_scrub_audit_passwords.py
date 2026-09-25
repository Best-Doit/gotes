from django.db import migrations


def scrub_passwords(apps, schema_editor):
    AuditLog = apps.get_model("core", "AuditLog")
    logs = AuditLog.objects.using(schema_editor.connection.alias).filter(object_type="core.User")
    for log in logs.iterator(chunk_size=500):
        changed = []
        for field in ("before", "after"):
            data = getattr(log, field)
            if isinstance(data, dict) and "password" in data:
                data.pop("password")
                changed.append(field)
        if changed:
            log.save(using=schema_editor.connection.alias, update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("core", "0009_add_received_email_event")]
    operations = [migrations.RunPython(scrub_passwords, migrations.RunPython.noop)]
