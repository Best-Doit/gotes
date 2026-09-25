from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("core", "0010_scrub_audit_passwords")]
    operations = [migrations.CreateModel(
        name="LoginThrottle",
        fields=[
            ("key", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("attempts", models.PositiveIntegerField(default=0)),
            ("window_started", models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
        ],
    )]
