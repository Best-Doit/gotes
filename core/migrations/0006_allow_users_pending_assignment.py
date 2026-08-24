from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_update_role_labels"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SUPERADMIN", "Superusuario"),
                    ("COMPANY_ADMIN", "Administrador de empresa"),
                    ("MANAGER", "Encargado"),
                    ("RECONCILER", "Conciliador comercial"),
                    ("AUDITOR", "Auditor"),
                ],
                default="",
                max_length=20,
                verbose_name="rol",
            ),
        ),
    ]
