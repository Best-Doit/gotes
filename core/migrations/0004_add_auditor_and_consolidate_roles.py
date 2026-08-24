from django.db import migrations, models


def convert_operators_to_managers(apps, schema_editor):
    user_model = apps.get_model("core", "User")
    user_model.objects.filter(role="OPERATOR").update(role="MANAGER")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_alter_user_role"),
    ]

    operations = [
        migrations.RunPython(convert_operators_to_managers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPERADMIN", "Superadministrador"),
                    ("COMPANY_ADMIN", "Administrador de empresa"),
                    ("MANAGER", "Encargado"),
                    ("RECONCILER", "Responsable de conciliación comercial"),
                    ("AUDITOR", "Auditor"),
                ],
                default="MANAGER",
                max_length=20,
                verbose_name="rol",
            ),
        ),
    ]
