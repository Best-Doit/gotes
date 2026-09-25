"""Audit probes: passing assertions CONFIRM existing defects, not secure behavior."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(os.environ.get('GOTES_AUDIT_ROOT', Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
AUDIT_TEMP = tempfile.TemporaryDirectory(prefix='gotes-audit-')
os.environ['GOTES_DATA_DIR'] = str(Path(AUDIT_TEMP.name) / 'data')
os.environ['GOTES_MEDIA_ROOT'] = str(Path(AUDIT_TEMP.name) / 'media')
# Never connect to an existing deployment database or mail server.
os.environ.pop('POSTGRES_HOST', None)
import django
django.setup()
from django.conf import settings
settings.DATABASES['default']['NAME'] = ':memory:'
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.ALLOWED_HOSTS = ['testserver']
settings.SECURE_SSL_REDIRECT = False
settings.STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
import logging
logging.disable(logging.CRITICAL)
from django.test import TestCase, Client
from django.test.runner import DiscoverRunner
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from core.models import Company, Branch, User, Product, Transfer, TransferItem, Evidence, ReceiptItem, Incident, AuditLog, EmailOutbox
from core.forms import TransferForm, ExpectedReceiptFormSet
from core.services import prepare_transfer, dispatch_transfer, get_or_start_receipt, confirm_receipt, snapshot
from core.email_notifications import _claim_pending_deliveries

class AuditProbes(TestCase):
    def setUp(self):
        self.company = Company.objects.create(code='audit-company', name='Audit Company')
        self.origin = Branch.objects.create(company=self.company, code='O', name='Origin')
        self.dest = Branch.objects.create(company=self.company, code='D', name='Destination')
        self.manager = User.objects.create_user(username='origin', password='audit-password', company=self.company, branch=self.origin, role=User.Role.MANAGER)
        self.receiver = User.objects.create_user(username='receiver', password='audit-password', company=self.company, branch=self.dest, role=User.Role.MANAGER)
        self.admin = User.objects.create_user(username='admin', password='audit-password', company=self.company, role=User.Role.COMPANY_ADMIN)
        self.product = Product.objects.create(company=self.company, code='P', name='Product', category='General')
        self.extra = Product.objects.create(company=self.company, code='X', name='Extra', category='General')
        self.transfer = Transfer.objects.create(company=self.company, origin=self.origin, destination=self.dest, created_by=self.manager)
        self.item = TransferItem.objects.create(transfer=self.transfer, product=self.product, quantity_sent=10)
        self.client = Client(raise_request_exception=False)
        self.client.force_login(self.manager)

    def evidence(self, kind, user):
        return Evidence.objects.create(transfer=self.transfer, type=kind, uploaded_by=user, file=SimpleUploadedFile('proof.jpg', b'\xff\xd8\xffsynthetic', content_type='image/jpeg'))

    def dispatch(self):
        prepare_transfer(self.transfer, self.manager)
        self.evidence(Evidence.Type.DISPATCH, self.manager)
        dispatch_transfer(self.transfer, self.manager)

    def receipt(self):
        self.dispatch()
        return get_or_start_receipt(self.transfer, self.receiver)

    def receipt_data(self, receipt, quantity='10'):
        return {'expected-TOTAL_FORMS': '1', 'expected-INITIAL_FORMS': '1', 'expected-0-id': receipt.items.get().pk, 'expected-0-quantity_received': quantity, 'expected-0-observation': '', 'unexpected-TOTAL_FORMS': '0', 'unexpected-INITIAL_FORMS': '0'}

    def test_unexpected_product_cannot_be_added(self):
        receipt = self.receipt()
        self.client.force_login(self.receiver)
        data = self.receipt_data(receipt)
        data.update({'unexpected-TOTAL_FORMS': '1', 'unexpected-0-product': self.extra.pk, 'unexpected-0-quantity_received': '2', 'unexpected-0-observation': 'Extra'})
        response = self.client.post(f'/traspasos/{self.transfer.uuid}/recibir/', data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Una línea sin producto enviado debe marcarse como inesperada.')
        self.assertFalse(receipt.items.filter(is_unexpected=True).exists())

    def test_duplicate_catalog_codes_raise_500(self):
        self.client.force_login(self.admin)
        for path, data in [('/empresa/productos/', {'code': 'P', 'name': 'duplicate', 'category': 'General'}), ('/empresa/sucursales/', {'code': 'O', 'name': 'duplicate', 'is_active': 'on'})]:
            with self.subTest(path=path):
                response = self.client.post(path, data)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.exc_info[0].__name__, 'ValidationError')

    def test_malformed_filters_raise_500(self):
        for path in ['/traspasos/?origin=abc', '/traspasos/?date_from=2026-02-31', '/reportes/?date_from=2026-02-31']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.exc_info[0].__name__, 'ValueError')

    def test_disabled_company_and_branch_can_still_operate(self):
        self.company.is_active = False
        self.company.save()
        self.origin.is_active = False
        self.origin.save()
        self.assertTrue(self.client.login(username='origin', password='audit-password'))
        response = self.client.post(f'/traspasos/{self.transfer.uuid}/preparar/')
        self.assertEqual(response.status_code, 302)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.PREPARED)

    def test_get_receipt_changes_business_state(self):
        self.dispatch()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.receiver)
        response = self.client.get(f'/traspasos/{self.transfer.uuid}/recibir/')
        self.assertEqual(response.status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.RECEIVING)
        self.assertTrue(AuditLog.objects.filter(action='START_RECEIPT').exists())

    def test_edit_can_undo_dispatch_after_validation(self):
        original_save = TransferForm.save
        def interleaved_save(form, *args, **kwargs):
            # Deterministically insert a second request's completed transition.
            self.dispatch()
            return original_save(form, *args, **kwargs)
        data = {'destination': self.dest.pk, 'notes': 'late draft', 'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '1', 'items-0-id': self.item.pk, 'items-0-product': self.product.pk, 'items-0-quantity_sent': '99', 'items-0-send_note': ''}
        with patch.object(TransferForm, 'save', interleaved_save):
            response = self.client.post(f'/traspasos/{self.transfer.uuid}/editar/', data)
        self.assertEqual(response.status_code, 302)
        self.transfer.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.DRAFT)
        self.assertEqual(self.item.quantity_sent, Decimal('99'))
        self.assertIsNone(self.transfer.dispatched_at)
        self.assertTrue(AuditLog.objects.filter(action='DISPATCH').exists())

    def test_receipt_edit_changes_confirmed_quantity(self):
        receipt = self.receipt()
        self.evidence(Evidence.Type.RECEIPT, self.receiver)
        self.client.force_login(self.receiver)
        original_save = ExpectedReceiptFormSet.save
        def interleaved_save(formset, *args, **kwargs):
            confirm_receipt(self.transfer, self.receiver)
            return original_save(formset, *args, **kwargs)
        with patch.object(ExpectedReceiptFormSet, 'save', interleaved_save):
            response = self.client.post(f'/traspasos/{self.transfer.uuid}/recibir/', self.receipt_data(receipt, '2'))
        self.assertEqual(response.status_code, 302)
        self.transfer.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.RECEIVED)
        self.assertEqual(receipt.status, 'CONFIRMED')
        self.assertEqual(receipt.items.get().quantity_received, Decimal('2'))
        self.assertFalse(Incident.objects.filter(transfer=self.transfer).exists())

    def test_csv_keeps_formula_as_executable_cell(self):
        self.origin.name = '=1+1'
        self.origin.save()
        response = self.client.get('/traspasos/exportar.csv')
        self.assertEqual(response.status_code, 200)
        import csv
        rows = list(csv.reader(response.content.decode('utf-8-sig').splitlines()))
        self.assertEqual(rows[1][2], '=1+1')

    def test_audit_stores_password_hash(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/empresa/asignaciones/{self.receiver.pk}/', {'role': User.Role.AUDITOR, 'branch': ''})
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.get(action='MANAGE_ASSIGNMENT')
        self.assertEqual(log.before['password'], self.receiver.password)
        self.assertEqual(log.after['password'], self.receiver.password)

    def test_malformed_xlsx_raises_500(self):
        self.client.force_login(self.admin)
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('unrelated.txt', 'not a workbook')
        response = self.client.post('/empresa/productos/importar/', {'file': SimpleUploadedFile('broken.xlsx', data.getvalue())})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.exc_info[0].__name__, 'KeyError')

    def test_reports_count_drafts_and_cancelled_as_pending_receipt(self):
        Transfer.objects.create(company=self.company, origin=self.origin, destination=self.dest, created_by=self.manager, status=Transfer.Status.CANCELLED)
        self.client.force_login(self.admin)
        response = self.client.get('/reportes/')
        row = next(r for r in response.context['branch_rows'] if r['branch'].pk == self.dest.pk)
        self.assertEqual(row['pending_receipt'], 2)
        self.assertEqual(response.context['in_transit'], 0)

    def test_last_email_attempt_stays_processing_forever(self):
        delivery = EmailOutbox.objects.create(transfer=self.transfer, recipient=self.receiver, recipient_email='audit@example.test', event='TRANSFER_DISPATCHED', subject='audit', body='audit', status='PROCESSING', attempts=settings.EMAIL_OUTBOX_MAX_ATTEMPTS)
        EmailOutbox.objects.filter(pk=delivery.pk).update(updated_at=timezone.now() - timedelta(days=1))
        self.assertEqual(_claim_pending_deliveries(50), [])
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'PROCESSING')

if __name__ == '__main__':
    print('NOTE: passing probes confirm the documented defects; this is not a security regression suite.', flush=True)
    try:
        failed = DiscoverRunner(verbosity=2, interactive=False).run_tests(['__main__.AuditProbes'])
    finally:
        from django.db import connections
        connections.close_all()
        AUDIT_TEMP.cleanup()
    raise SystemExit(bool(failed))
