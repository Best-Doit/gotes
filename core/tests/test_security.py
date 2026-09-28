"""Regression coverage for the September 2026 audit."""
import csv
import importlib
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from queue import Queue
from threading import Event
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections, close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from core.email_notifications import _claim_pending_deliveries
from core.forms import TransferForm, ExpectedReceiptFormSet
from core.models import Company, Branch, User, Product, Transfer, TransferItem, Evidence, Receipt, Incident, AuditLog, EmailOutbox, LoginThrottle
from core.product_import import parse_product_workbook, InvalidProductWorkbook, MAX_ARCHIVE_BYTES
from core.services import prepare_transfer, dispatch_transfer, get_or_start_receipt, confirm_receipt, visible_transfers


class AuditFixtures:
    def setUp(self):
        super().setUp()
        self.media = tempfile.TemporaryDirectory(prefix='gotes-regression-')
        self.addCleanup(self.media.cleanup)
        self.options = override_settings(MEDIA_ROOT=self.media.name, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
        self.options.enable()
        self.addCleanup(self.options.disable)
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
        return {'expected-TOTAL_FORMS': '1', 'expected-INITIAL_FORMS': '1', 'expected-0-id': receipt.items.get(is_unexpected=False).pk, 'expected-0-quantity_received': quantity, 'expected-0-observation': '', 'unexpected-TOTAL_FORMS': '0', 'unexpected-INITIAL_FORMS': '0'}

    def edit_data(self):
        return {'destination': self.dest.pk, 'notes': 'edited', 'items-TOTAL_FORMS': '1', 'items-INITIAL_FORMS': '1', 'items-0-id': self.item.pk, 'items-0-product': self.product.pk, 'items-0-quantity_sent': '99', 'items-0-send_note': ''}


class SecurityRegressionTests(AuditFixtures, TestCase):
    def test_evidence_json_returns_saved_receipt_destination(self):
        self.receipt()
        self.client.force_login(self.receiver)
        response = self.client.post(reverse('upload_evidence', args=[self.transfer.uuid]), {
            'type': Evidence.Type.RECEIPT, '_return_to': 'receipt',
            'file': SimpleUploadedFile('camera.jpg', b'\xff\xd8\xffcamera-proof', content_type='image/jpeg'),
        }, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertIn('step=4&evidence=1', response.json()['redirect_url'])
        self.assertEqual(self.transfer.evidences.filter(type=Evidence.Type.RECEIPT).count(), 1)

    @override_settings(EVIDENCE_MAX_FILE_SIZE_MB=1)
    def test_evidence_json_explains_size_and_format_rejections(self):
        self.receipt()
        self.client.force_login(self.receiver)
        for name, content, mime, expected in [
            ('camera.jpg', b'\xff\xd8\xff' + b'x' * 1024 * 1024, 'image/jpeg', 'supera el límite'),
            ('camera.heic', b'HEIC', 'image/heic', 'Formato no permitido'),
        ]:
            with self.subTest(name=name):
                response = self.client.post(reverse('upload_evidence', args=[self.transfer.uuid]), {
                    'type': Evidence.Type.RECEIPT, '_return_to': 'receipt',
                    'file': SimpleUploadedFile(name, content, content_type=mime),
                }, HTTP_ACCEPT='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])
                self.assertIn(expected, response.json()['error'])
        self.assertFalse(self.transfer.evidences.filter(type=Evidence.Type.RECEIPT).exists())

    def test_evidence_rejection_without_javascript_preserves_reason(self):
        self.receipt()
        self.client.force_login(self.receiver)
        response = self.client.post(reverse('upload_evidence', args=[self.transfer.uuid]), {
            'type': Evidence.Type.RECEIPT, '_return_to': 'receipt',
            'file': SimpleUploadedFile('camera.heic', b'HEIC', content_type='image/heic'),
        }, follow=True)
        self.assertContains(response, 'Formato no permitido')
        self.assertFalse(self.transfer.evidences.filter(type=Evidence.Type.RECEIPT).exists())

    def test_evidence_json_does_not_bypass_role_or_state_permissions(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('upload_evidence', args=[self.transfer.uuid]), {
            'type': Evidence.Type.DISPATCH,
            'file': SimpleUploadedFile('camera.jpg', b'\xff\xd8\xffcamera-proof', content_type='image/jpeg'),
        }, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.transfer.evidences.exists())

    def test_unexpected_product_generates_incident(self):
        receipt = self.receipt()
        self.client.force_login(self.receiver)
        data = self.receipt_data(receipt)
        data.update({'unexpected-TOTAL_FORMS': '1', 'unexpected-0-product': self.extra.pk, 'unexpected-0-quantity_received': '2'})
        response = self.client.post(reverse('receipt_edit', args=[self.transfer.uuid]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(receipt.items.get(is_unexpected=True).quantity_received, Decimal('2'))
        self.evidence(Evidence.Type.RECEIPT, self.receiver)
        confirm_receipt(self.transfer, self.receiver)
        self.assertTrue(Incident.objects.get(transfer=self.transfer).differences.filter(type='UNEXPECTED').exists())

    def test_unexpected_product_requires_quantity_and_cannot_duplicate_expected(self):
        receipt = self.receipt()
        self.client.force_login(self.receiver)
        data = self.receipt_data(receipt)
        data.update({'unexpected-TOTAL_FORMS': '1', 'unexpected-0-product': self.extra.pk, 'unexpected-0-quantity_received': ''})
        response = self.client.post(reverse('receipt_edit', args=[self.transfer.uuid]), data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['unexpected'].forms[0].errors['quantity_received'])
        data.update({'unexpected-0-product': self.product.pk, 'unexpected-0-quantity_received': '2'})
        response = self.client.post(reverse('receipt_edit', args=[self.transfer.uuid]), data)
        self.assertTrue(response.context['unexpected'].forms[0].errors['product'])
        self.assertEqual(receipt.items.count(), 1)

    def test_duplicate_catalog_codes_show_form_errors(self):
        self.client.force_login(self.admin)
        for path, data in [('/empresa/productos/', {'code': 'P', 'name': 'duplicate', 'category': 'General'}), ('/empresa/sucursales/', {'code': 'O', 'name': 'duplicate', 'is_active': 'on'})]:
            with self.subTest(path=path):
                response = self.client.post(path, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn('code', response.context['form'].errors)

    def test_malformed_filters_return_400(self):
        for path in ['/traspasos/?origin=abc', '/traspasos/?origin=-1', '/traspasos/?origin=' + '9'*40, '/traspasos/?date_from=2026-02-31', '/reportes/?date_from=2026-02-31', '/traspasos/exportar.csv?product=bad', '/reportes/?date_from=2026-09-25&date_to=2026-09-24']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 400)

    def test_suspension_rejects_login_existing_sessions_and_services(self):
        for model, obj in [(Company, self.company), (Branch, self.origin)]:
            with self.subTest(model=model):
                model.objects.filter(pk=obj.pk).update(is_active=False)
                self.assertFalse(self.client.login(username='origin', password='audit-password'))
                self.assertEqual(self.client.get('/').status_code, 302)
                self.assertNotIn('_auth_user_id', self.client.session)
                with self.assertRaises(PermissionDenied):
                    prepare_transfer(self.transfer, self.manager)
                self.assertFalse(visible_transfers(self.manager).exists())
                model.objects.filter(pk=obj.pk).update(is_active=True)
                self.assertEqual(self.client.get('/').status_code, 302)
                self.client.force_login(self.manager)

    def test_get_receipt_is_read_only_and_start_requires_csrf(self):
        self.dispatch()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.receiver)
        self.assertEqual(client.get(reverse('receipt_edit', args=[self.transfer.uuid])).status_code, 200)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.DISPATCHED)
        self.assertFalse(Receipt.objects.filter(transfer=self.transfer).exists())
        url = reverse('receipt_start', args=[self.transfer.uuid])
        self.assertEqual(client.get(url).status_code, 405)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(url, {'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, 302)
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.RECEIVING)

    def test_stale_edits_cannot_change_dispatched_or_confirmed_data(self):
        self.dispatch()
        self.assertEqual(self.client.post(reverse('transfer_edit', args=[self.transfer.uuid]), self.edit_data()).status_code, 403)
        receipt = get_or_start_receipt(self.transfer, self.receiver)
        self.evidence(Evidence.Type.RECEIPT, self.receiver)
        confirm_receipt(self.transfer, self.receiver)
        self.client.force_login(self.receiver)
        response = self.client.post(reverse('receipt_edit', args=[self.transfer.uuid]), self.receipt_data(receipt, '2'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(receipt.items.get().quantity_received, Decimal('10'))

    def test_csv_neutralizes_formula_prefixes(self):
        for name in ['=1+1', '+1+1', '-1+1', '@SUM(1)', '  =1+1', '\t=1+1', '\n=1+1']:
            with self.subTest(name=name):
                self.origin.name = name
                self.origin.save()
                response = self.client.get('/traspasos/exportar.csv')
                rows = list(csv.reader(__import__('io').StringIO(response.content.decode('utf-8-sig'))))
                self.assertEqual(rows[1][2], "'" + name)

    def test_audit_excludes_password_and_migration_scrubs_existing_hashes(self):
        self.client.force_login(self.admin)
        response = self.client.post(f'/empresa/asignaciones/{self.receiver.pk}/', {'role': User.Role.AUDITOR, 'branch': ''})
        self.assertEqual(response.status_code, 302)
        log = AuditLog.objects.get(action='MANAGE_ASSIGNMENT')
        self.assertNotIn('password', log.before)
        self.assertNotIn('password', log.after)
        log.before['password'] = 'synthetic-old-hash'
        log.save()
        migration = importlib.import_module('core.migrations.0010_scrub_audit_passwords')
        migration.scrub_passwords(apps, type('Editor', (), {'connection': connection})())
        log.refresh_from_db()
        self.assertNotIn('password', log.before)
        self.assertEqual(log.before['username'], self.receiver.username)

    def test_malformed_xlsx_returns_form_error(self):
        self.client.force_login(self.admin)
        data = BytesIO()
        with ZipFile(data, 'w') as archive:
            archive.writestr('unrelated.txt', 'not a workbook')
        response = self.client.post('/empresa/productos/importar/', {'file': SimpleUploadedFile('broken.xlsx', data.getvalue())})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['import_form'].errors['file'])

    def test_excel_rejects_large_dimensions_xml_entities_and_compression(self):
        workbook = Workbook()
        workbook.active['A1'] = 'Código'
        workbook.active['A10002'] = 'too far'
        data = BytesIO()
        workbook.save(data)
        with self.assertRaises(InvalidProductWorkbook):
            parse_product_workbook(data)
        for entry, content in [('xl/sharedStrings.xml', b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'), ('xl/large.xml', b' ' * (MAX_ARCHIVE_BYTES + 1))]:
            data = BytesIO()
            with ZipFile(data, 'w', compression=ZIP_DEFLATED) as archive:
                archive.writestr(entry, content)
            with self.assertRaises(InvalidProductWorkbook):
                parse_product_workbook(data)

    def test_reports_exclude_draft_and_cancelled_pending_receipts(self):
        Transfer.objects.create(company=self.company, origin=self.origin, destination=self.dest, created_by=self.manager, status=Transfer.Status.CANCELLED)
        self.client.force_login(self.admin)
        response = self.client.get('/reportes/')
        row = next(r for r in response.context['branch_rows'] if r['branch'].pk == self.dest.pk)
        self.assertEqual(row['pending_receipt'], 0)
        self.assertEqual(response.context['in_transit'], 0)

    def test_final_email_attempt_expires_without_retry(self):
        delivery = EmailOutbox.objects.create(transfer=self.transfer, recipient=self.receiver, recipient_email='audit@example.test', event='TRANSFER_DISPATCHED', subject='audit', body='audit', status='PROCESSING', attempts=settings.EMAIL_OUTBOX_MAX_ATTEMPTS)
        EmailOutbox.objects.filter(pk=delivery.pk).update(updated_at=timezone.now() - timedelta(days=1))
        self.assertEqual(_claim_pending_deliveries(50), [])
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailOutbox.Status.FAILED)

    @override_settings(LOGIN_RATE_MAX_ATTEMPTS=2, LOGIN_RATE_WINDOW_SECONDS=900)
    def test_login_throttle_shared_by_admin_and_operational_login(self):
        client = Client()
        self.assertEqual(client.post('/login/', {'username': 'missing', 'password': 'bad'}).status_code, 200)
        self.assertEqual(client.post('/django-admin/login/', {'username': 'missing', 'password': 'bad'}).status_code, 200)
        response = client.post('/login/', {'username': 'origin', 'password': 'audit-password'}, HTTP_X_FORWARDED_FOR='192.0.2.1')
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '900')
        LoginThrottle.objects.update(window_started=timezone.now() - timedelta(seconds=901))
        self.assertEqual(client.post('/login/', {'username': 'origin', 'password': 'audit-password'}).status_code, 302)

    def test_production_requires_secret_and_defaults_to_secure_cookies(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith(('DJANGO_', 'POSTGRES_', 'GOTES_', 'GOTS_'))}
        env.update(DJANGO_DEBUG='0', GOTES_DATA_DIR=self.media.name)
        result = subprocess.run([sys.executable, '-c', 'import config.settings'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', result.stderr)
        env['DJANGO_SECRET_KEY'] = 'audit-test-only-8b271fed1e5a4ae19d6196c9339fcd4e-secret'
        result = subprocess.run([sys.executable, '-c', 'from config import settings as s; assert s.SECURE_SSL_REDIRECT and s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @override_settings(
        DEBUG=False,
        SECRET_KEY='audit-test-only-8b271fed1e5a4ae19d6196c9339fcd4e-secret',
        SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
        SECURE_HSTS_SECONDS=31536000, SECURE_HSTS_INCLUDE_SUBDOMAINS=False,
        SECURE_HSTS_PRELOAD=False,
    )
    def test_production_check_blocks_insecure_cookies_without_forcing_hsts_optins(self):
        from io import StringIO
        call_command('check_production_security', stdout=StringIO())
        with override_settings(SESSION_COOKIE_SECURE=False):
            with self.assertRaises(CommandError):
                call_command('check_production_security', stdout=StringIO())


@skipUnlessDBFeature('has_select_for_update')
class WorkflowConcurrencyTests(AuditFixtures, TransactionTestCase):
    def _thread(self, action):
        close_old_connections()
        try:
            return action()
        finally:
            connections.close_all()

    def _assert_waiting_for_lock(self, pid):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute('SELECT cardinality(pg_blocking_pids(%s))', [pid])
                if cursor.fetchone()[0]:
                    return
            time.sleep(0.02)
        self.fail('The competing transition was not blocked by the edit transaction.')

    def _race(self, form_class, edit_action, competing_action):
        entered, release = Event(), Event()
        pid_queue = Queue()
        original = form_class.is_valid
        def pause_after_validation(form):
            valid = original(form)
            entered.set()
            if not release.wait(10):
                raise TimeoutError('Edit test did not release validation.')
            return valid
        def compete():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pid_queue.put(cursor.fetchone()[0])
            return competing_action()
        with ThreadPoolExecutor(max_workers=2) as pool, patch.object(form_class, 'is_valid', pause_after_validation):
            edit = pool.submit(self._thread, edit_action)
            try:
                self.assertTrue(entered.wait(10), 'Edit did not reach validation.')
                competing = pool.submit(self._thread, compete)
                self._assert_waiting_for_lock(pid_queue.get(timeout=5))
            finally:
                release.set()
            response = edit.result(timeout=10)
            self.assertEqual(response.status_code, 302)
            competing.result(timeout=10)

    def test_dispatch_waits_for_draft_edit(self):
        self.evidence(Evidence.Type.DISPATCH, self.manager)
        def edit():
            client = Client()
            client.force_login(self.manager)
            return client.post(reverse('transfer_edit', args=[self.transfer.uuid]), self.edit_data())
        def dispatch():
            prepare_transfer(self.transfer, self.manager)
            dispatch_transfer(self.transfer, self.manager)
        self._race(TransferForm, edit, dispatch)
        self.transfer.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.DISPATCHED)
        self.assertIsNotNone(self.transfer.dispatched_at)
        self.assertEqual(self.item.quantity_sent, Decimal('99'))

    def test_confirmation_waits_for_receipt_edit_and_records_difference(self):
        receipt = self.receipt()
        self.evidence(Evidence.Type.RECEIPT, self.receiver)
        data = self.receipt_data(receipt, '2')
        def edit():
            client = Client()
            client.force_login(self.receiver)
            return client.post(reverse('receipt_edit', args=[self.transfer.uuid]), data)
        self._race(ExpectedReceiptFormSet, edit, lambda: confirm_receipt(self.transfer, self.receiver))
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, Transfer.Status.RECEIVED_DIFFERENCES)
        difference = Incident.objects.get(transfer=self.transfer).differences.get(type='MISSING')
        self.assertEqual(difference.quantity_received, Decimal('2'))
