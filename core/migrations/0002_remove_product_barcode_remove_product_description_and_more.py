from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='barcode',
        ),
        migrations.RemoveField(
            model_name='product',
            name='description',
        ),
        migrations.RemoveField(
            model_name='product',
            name='is_active',
        ),
        migrations.RemoveField(
            model_name='product',
            name='unit',
        ),
        migrations.AlterField(
            model_name='product',
            name='category',
            field=models.CharField(max_length=100, verbose_name='categoría'),
        ),
    ]
