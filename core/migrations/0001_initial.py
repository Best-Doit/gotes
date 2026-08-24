import core.models
import core.validators
import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=30, verbose_name='código')),
                ('name', models.CharField(max_length=160, verbose_name='nombre')),
                ('address', models.CharField(blank=True, max_length=255, verbose_name='dirección')),
                ('phone', models.CharField(blank=True, max_length=40, verbose_name='teléfono')),
                ('is_active', models.BooleanField(default=True, verbose_name='activa')),
            ],
            options={
                'verbose_name': 'sucursal',
                'verbose_name_plural': 'sucursales',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.SlugField(max_length=30, unique=True, verbose_name='código')),
                ('name', models.CharField(max_length=160, verbose_name='nombre')),
                ('is_active', models.BooleanField(default=True, verbose_name='activa')),
            ],
            options={
                'verbose_name': 'empresa',
                'verbose_name_plural': 'empresas',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('role', models.CharField(choices=[('SUPERADMIN', 'Superadministrador'), ('COMPANY_ADMIN', 'Administrador de empresa'), ('MANAGER', 'Encargado'), ('OPERATOR', 'Operador')], default='OPERATOR', max_length=20, verbose_name='rol')),
                ('phone', models.CharField(blank=True, max_length=40, verbose_name='teléfono')),
                ('allow_dispatch', models.BooleanField(blank=True, null=True, verbose_name='puede despachar')),
                ('allow_close', models.BooleanField(blank=True, null=True, verbose_name='puede cerrar')),
                ('allow_cancel', models.BooleanField(blank=True, null=True, verbose_name='puede anular')),
                ('allow_resolve_incident', models.BooleanField(blank=True, null=True, verbose_name='puede resolver incidencias')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='users', to='core.branch', verbose_name='sucursal')),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='users', to='core.company', verbose_name='empresa')),
            ],
            options={
                'verbose_name': 'usuario',
                'verbose_name_plural': 'usuarios',
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.AddField(
            model_name='branch',
            name='company',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='branches', to='core.company', verbose_name='empresa'),
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(db_index=True, max_length=40)),
                ('object_type', models.CharField(max_length=80)),
                ('object_uuid', models.CharField(db_index=True, max_length=80)),
                ('description', models.TextField()),
                ('before', models.JSONField(blank=True, null=True)),
                ('after', models.JSONField(blank=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='audit_logs', to='core.branch')),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='audit_logs', to='core.company')),
            ],
            options={
                'verbose_name': 'registro de auditoría',
                'verbose_name_plural': 'registros de auditoría',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='Incident',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('year', models.PositiveSmallIntegerField(editable=False)),
                ('sequence', models.PositiveIntegerField(editable=False)),
                ('code', models.CharField(editable=False, max_length=30)),
                ('status', models.CharField(choices=[('OPEN', 'Abierta'), ('IN_REVIEW', 'En revisión'), ('RESOLVED', 'Resuelta')], db_index=True, default='OPEN', max_length=20)),
                ('summary', models.TextField(blank=True)),
                ('resolution_type', models.CharField(blank=True, choices=[('FOUND', 'Producto encontrado'), ('ACCEPTED', 'Diferencia aceptada'), ('CORRECTED_EXTERNAL', 'Corregido en sistema comercial'), ('RETURNED', 'Producto devuelto'), ('OTHER', 'Otro')], max_length=30)),
                ('resolution_text', models.TextField(blank=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incidents', to='core.company')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_incidents', to=settings.AUTH_USER_MODEL)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='resolved_incidents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'incidencia',
                'verbose_name_plural': 'incidencias',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=60, verbose_name='código')),
                ('barcode', models.CharField(blank=True, max_length=80, verbose_name='código de barras')),
                ('name', models.CharField(max_length=200, verbose_name='nombre')),
                ('description', models.TextField(blank=True, verbose_name='descripción')),
                ('category', models.CharField(blank=True, max_length=100, verbose_name='categoría')),
                ('unit', models.CharField(default='Unidad', max_length=40, verbose_name='unidad')),
                ('is_active', models.BooleanField(default=True, verbose_name='activo')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='core.company', verbose_name='empresa')),
            ],
            options={
                'verbose_name': 'producto',
                'verbose_name_plural': 'productos',
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='IncidentDifference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.CharField(choices=[('MISSING', 'Faltante'), ('SURPLUS', 'Sobrante'), ('UNEXPECTED', 'Producto inesperado'), ('DAMAGED', 'Producto dañado')], max_length=20)),
                ('quantity_sent', models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ('quantity_received', models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ('observation', models.CharField(blank=True, max_length=255)),
                ('incident', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='differences', to='core.incident')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incident_differences', to='core.product')),
            ],
            options={
                'verbose_name': 'diferencia',
                'verbose_name_plural': 'diferencias',
                'ordering': ('product__name', 'type'),
            },
        ),
        migrations.CreateModel(
            name='Sequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('TRANSFER', 'Traspaso'), ('INCIDENT', 'Incidencia')], max_length=20)),
                ('year', models.PositiveSmallIntegerField()),
                ('next_value', models.PositiveIntegerField(default=1)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sequences', to='core.company')),
            ],
        ),
        migrations.CreateModel(
            name='Transfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('year', models.PositiveSmallIntegerField(editable=False)),
                ('sequence', models.PositiveIntegerField(editable=False)),
                ('code', models.CharField(editable=False, max_length=30)),
                ('status', models.CharField(choices=[('DRAFT', 'Borrador'), ('PREPARED', 'Preparado'), ('DISPATCHED', 'Despachado'), ('RECEIVING', 'En recepción'), ('RECEIVED', 'Recibido'), ('RECEIVED_DIFFERENCES', 'Recibido con diferencias'), ('CLOSED', 'Cerrado'), ('CANCELLED', 'Anulado')], db_index=True, default='DRAFT', max_length=30, verbose_name='estado')),
                ('notes', models.TextField(blank=True, verbose_name='observaciones')),
                ('prepared_at', models.DateTimeField(blank=True, null=True)),
                ('dispatched_at', models.DateTimeField(blank=True, null=True)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('cancellation_reason', models.TextField(blank=True)),
                ('cancelled_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cancelled_transfers', to=settings.AUTH_USER_MODEL)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='closed_transfers', to=settings.AUTH_USER_MODEL)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfers', to='core.company', verbose_name='empresa')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_transfers', to=settings.AUTH_USER_MODEL)),
                ('destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incoming_transfers', to='core.branch', verbose_name='destino')),
                ('dispatched_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='dispatched_transfers', to=settings.AUTH_USER_MODEL)),
                ('origin', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='outgoing_transfers', to='core.branch', verbose_name='origen')),
                ('prepared_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='prepared_transfers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'traspaso',
                'verbose_name_plural': 'traspasos',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='Receipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('DRAFT', 'Borrador'), ('CONFIRMED', 'Confirmada')], default='DRAFT', max_length=20)),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, verbose_name='observaciones')),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='confirmed_receipts', to=settings.AUTH_USER_MODEL)),
                ('started_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='started_receipts', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='receipt', to='core.transfer', verbose_name='traspaso')),
            ],
            options={
                'verbose_name': 'recepción',
                'verbose_name_plural': 'recepciones',
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.CharField(max_length=255)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='core.transfer')),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.AddField(
            model_name='incident',
            name='transfer',
            field=models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='incident', to='core.transfer'),
        ),
        migrations.CreateModel(
            name='Evidence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('type', models.CharField(choices=[('PREPARATION', 'Preparación'), ('DISPATCH', 'Salida'), ('RECEIPT', 'Recepción'), ('INCIDENT', 'Incidencia'), ('CORRECTION', 'Corrección')], max_length=20, verbose_name='tipo')),
                ('file', models.FileField(upload_to=core.models.evidence_upload_path, validators=[core.validators.validate_evidence_file], verbose_name='archivo')),
                ('original_name', models.CharField(editable=False, max_length=255)),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='descripción')),
                ('objected', models.BooleanField(default=False, verbose_name='objetada')),
                ('objection_reason', models.TextField(blank=True, verbose_name='motivo de objeción')),
                ('correction_of', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='corrections', to='core.evidence', verbose_name='corrige a')),
                ('uploaded_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='uploaded_evidences', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='evidences', to='core.transfer', verbose_name='traspaso')),
            ],
            options={
                'verbose_name': 'evidencia',
                'verbose_name_plural': 'evidencias',
                'ordering': ('created_at',),
            },
        ),
        migrations.CreateModel(
            name='CommercialRegistration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('external_reference', models.CharField(max_length=120, verbose_name='referencia externa')),
                ('external_date', models.DateField(verbose_name='fecha en sistema comercial')),
                ('notes', models.TextField(blank=True, verbose_name='observaciones')),
                ('registered_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='commercial_registrations', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='commercial_registration', to='core.transfer')),
            ],
            options={
                'verbose_name': 'registro en sistema comercial',
                'verbose_name_plural': 'registros en sistema comercial',
            },
        ),
        migrations.CreateModel(
            name='TransferItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity_sent', models.DecimalField(decimal_places=3, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0.001'))], verbose_name='cantidad enviada')),
                ('send_note', models.CharField(blank=True, max_length=255, verbose_name='observación')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transfer_items', to='core.product', verbose_name='producto')),
                ('transfer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='core.transfer', verbose_name='traspaso')),
            ],
            options={
                'verbose_name': 'producto enviado',
                'verbose_name_plural': 'productos enviados',
                'ordering': ('product__name',),
            },
        ),
        migrations.CreateModel(
            name='ReceiptItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('quantity_received', models.DecimalField(decimal_places=3, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal('0'))], verbose_name='cantidad recibida')),
                ('is_unexpected', models.BooleanField(default=False, verbose_name='producto no enviado')),
                ('is_damaged', models.BooleanField(default=False, verbose_name='dañado')),
                ('observation', models.CharField(blank=True, max_length=255, verbose_name='observación')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receipt_items', to='core.product', verbose_name='producto')),
                ('receipt', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='items', to='core.receipt', verbose_name='recepción')),
                ('transfer_item', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='receipt_item', to='core.transferitem')),
            ],
            options={
                'verbose_name': 'producto recibido',
                'verbose_name_plural': 'productos recibidos',
                'ordering': ('product__name',),
            },
        ),
        migrations.AddConstraint(
            model_name='branch',
            constraint=models.UniqueConstraint(fields=('company', 'code'), name='unique_branch_code_per_company'),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.UniqueConstraint(fields=('company', 'code'), name='unique_product_code_per_company'),
        ),
        migrations.AddConstraint(
            model_name='sequence',
            constraint=models.UniqueConstraint(fields=('company', 'kind', 'year'), name='unique_company_kind_year_sequence'),
        ),
        migrations.AddIndex(
            model_name='transfer',
            index=models.Index(fields=['company', 'status', 'created_at'], name='core_transf_company_516d97_idx'),
        ),
        migrations.AddConstraint(
            model_name='transfer',
            constraint=models.UniqueConstraint(fields=('company', 'year', 'sequence'), name='unique_transfer_sequence_per_company_year'),
        ),
        migrations.AddConstraint(
            model_name='transfer',
            constraint=models.CheckConstraint(condition=models.Q(('origin', models.F('destination')), _negated=True), name='different_transfer_branches'),
        ),
        migrations.AddConstraint(
            model_name='incident',
            constraint=models.UniqueConstraint(fields=('company', 'year', 'sequence'), name='unique_incident_sequence_per_company_year'),
        ),
        migrations.AddConstraint(
            model_name='transferitem',
            constraint=models.UniqueConstraint(fields=('transfer', 'product'), name='unique_product_per_transfer'),
        ),
        migrations.AddConstraint(
            model_name='receiptitem',
            constraint=models.UniqueConstraint(condition=models.Q(('is_unexpected', True)), fields=('receipt', 'product'), name='unique_unexpected_product_per_receipt'),
        ),
    ]
