from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_add_auditor_and_consolidate_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPERADMIN", "Superusuario"),
                    ("COMPANY_ADMIN", "Administrador de empresa"),
                    ("MANAGER", "Encargado"),
                    ("RECONCILER", "Conciliador comercial"),
                    ("AUDITOR", "Auditor"),
                ],
                default="MANAGER",
                max_length=20,
                verbose_name="rol",
            ),
        ),
    ]
