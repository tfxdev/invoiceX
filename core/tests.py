import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Invoice, Product, Supplier, SupplierPaymentRecord


class SupplierLedgerTests(TestCase):
    """A supplier balance should move exactly like a customer's, but inverted:
    purchase bills raise what you owe, and recorded payments lower it."""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw')
        self.other = User.objects.create_user(username='intruder', password='pw')
        self.supplier = Supplier.objects.create(user=self.user, name='Acme Wholesale')
        self.other_supplier = Supplier.objects.create(user=self.other, name='Not Mine')
        self.client.force_login(self.user)

    def test_charge_then_payment_updates_due(self):
        SupplierPaymentRecord.objects.create(
            user=self.user, supplier=self.supplier, amount=Decimal('1000'),
            transaction_type='charge', note='opening')
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('1000'))

        pay = SupplierPaymentRecord.objects.create(
            user=self.user, supplier=self.supplier, amount=Decimal('400'),
            transaction_type='payment', payment_method='bkash', note='partial')
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('600'))

        pay.delete()
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('1000'))

    def test_supplier_list_payment_flow(self):
        SupplierPaymentRecord.objects.create(
            user=self.user, supplier=self.supplier, amount=Decimal('500'),
            transaction_type='charge')
        resp = self.client.post(reverse('supplier_list'), {
            'action': 'adjust_balance',
            'supplier_id': self.supplier.id,
            'trans_type': 'payment',
            'amount': '200',
            'payment_method': 'cash',
            'note': 'bill paid',
        })
        self.assertEqual(resp.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('300'))

    def test_ledger_api_returns_history_and_due(self):
        SupplierPaymentRecord.objects.create(
            user=self.user, supplier=self.supplier, amount=Decimal('750'),
            transaction_type='charge', note='stock bill')
        resp = self.client.get(reverse('supplier_ledger_api', args=[self.supplier.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['current_due'], 750.0)
        self.assertEqual(len(data['history']), 1)

    def test_ledger_api_is_scoped_to_owner(self):
        # The project redirects every 404 to the create-invoice page, so a
        # non-owner gets a redirect rather than the other user's data.
        resp = self.client.get(reverse('supplier_ledger_api', args=[self.other_supplier.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertNotContains(resp, 'Not Mine', status_code=302)

    def test_supplier_page_shows_payment_controls(self):
        resp = self.client.get(reverse('supplier_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Pay Supplier')
        self.assertContains(resp, 'openLedgerModal')


class PurchaseInvoicePayableTests(TestCase):
    """Creating/editing/deleting a purchase bill must keep supplier.due in sync."""

    def setUp(self):
        self.user = User.objects.create_user(username='owner', password='pw')
        self.client.force_login(self.user)
        self.supplier = Supplier.objects.create(user=self.user, name='Acme Wholesale')
        self.product = Product.objects.create(
            user=self.user, name='Napa', qty=10, price=Decimal('5'),
            cost_price=Decimal('3'))

    def _payload(self, due='600', invoice_id=None):
        data = {
            'invoice_type': 'purchase',
            'customer_id': str(self.supplier.id),
            'total_value': '1000',
            'payable_value': '1000',
            'paid_amount': '400',
            'due_amount': due,
            'authorized_signature': 'boss',
            'items': [{'product_id': self.product.id, 'quantity': 1,
                       'price': '1000', 'subtotal': '1000'}],
        }
        if invoice_id is not None:
            data['invoice_id'] = invoice_id
        return data

    def _save(self, payload):
        return self.client.post(
            reverse('save_invoice_api'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_create_purchase_invoice_raises_payable(self):
        resp = self._save(self._payload())
        self.assertEqual(resp.status_code, 200, resp.content)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('600'))

    def test_edit_purchase_invoice_adjusts_payable(self):
        invoice_id = self._save(self._payload()).json()['invoice_id']
        self._save(self._payload(due='200', invoice_id=invoice_id))
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('200'))

    def test_delete_purchase_invoice_reverses_payable(self):
        invoice_id = self._save(self._payload()).json()['invoice_id']
        resp = self.client.post(reverse('delete_invoice', args=[invoice_id]))
        self.assertEqual(resp.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.due, Decimal('0'))
        self.assertFalse(Invoice.objects.filter(id=invoice_id).exists())


class LandingLoginTests(TestCase):
    """The landing page is the sign-in page and the front door for anonymous users."""

    def setUp(self):
        self.user = User.objects.create_user(username='boss', password='secret123')

    def test_landing_serves_anonymous_visitors(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Everything your shop bills')
        self.assertContains(resp, 'Sign in')
        self.assertContains(resp, 'landing-bg.svg')

    def test_valid_login_redirects_to_dashboard(self):
        resp = self.client.post('/', {'username': 'boss', 'password': 'secret123'})
        self.assertRedirects(resp, '/dashboard/')
        self.assertEqual(self.client.get('/dashboard/').status_code, 200)

    def test_invalid_login_reshows_page_with_error(self):
        resp = self.client.post('/', {'username': 'boss', 'password': 'nope'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'lp-error')

    def test_authenticated_visitor_is_sent_to_dashboard(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get('/'), '/dashboard/')

    def test_protected_page_bounces_anonymous_to_landing(self):
        resp = self.client.get('/customers/')
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith('/?next='), resp.url)

    def test_logout_returns_to_landing(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post('/logout/'), '/')
        self.assertEqual(self.client.get('/customers/').status_code, 302)
