from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_remove_product_barcode_remove_product_description_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPERADMIN", "Superadministrador"),
                    ("COMPANY_ADMIN", "Administrador de empresa"),
                    ("RECONCILER", "Responsable de conciliación comercial"),
                    ("MANAGER", "Encargado"),
                    ("OPERATOR", "Operador"),
                ],
                default="OPERATOR",
                max_length=20,
                verbose_name="rol",
            ),
        ),
    ]
