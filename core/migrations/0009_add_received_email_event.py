from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0008_rename_pending_email_brand")]

    operations = [
        migrations.AlterField(
            model_name="emailoutbox",
            name="event",
            field=models.CharField(
                choices=[
                    ("TRANSFER_DISPATCHED", "Traspaso despachado"),
                    ("TRANSFER_RECEIVED", "Traspaso recibido"),
                    ("TRANSFER_RECONCILED", "Traspaso conciliado"),
                ],
                max_length=40,
            ),
        ),
    ]
