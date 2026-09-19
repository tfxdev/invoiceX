# Carry existing supplier payables (the unpaid part of past purchase bills) onto
# the new Supplier.due field, so the supplier screen and the dashboard agree.
#
# Each supplier with an outstanding balance gets a single ledger "charge" entry
# recording the carried-over amount, so the new ledger history is not blank.

from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def backfill_supplier_payables(apps, schema_editor):
    Supplier = apps.get_model('core', 'Supplier')
    Invoice = apps.get_model('core', 'Invoice')
    SupplierPaymentRecord = apps.get_model('core', 'SupplierPaymentRecord')

    for supplier in Supplier.objects.all():
        total = (Invoice.objects
                 .filter(invoice_type='purchase', supplier=supplier)
                 .aggregate(total=Sum('due_amount'))['total']) or Decimal('0.00')
        if total <= 0:
            continue

        Supplier.objects.filter(pk=supplier.pk).update(due=total)
        SupplierPaymentRecord.objects.create(
            user_id=supplier.user_id,
            supplier=supplier,
            amount=total,
            transaction_type='charge',
            payment_method='other',
            note='Opening payable carried over from existing purchase bills',
        )


def unbackfill_supplier_payables(apps, schema_editor):
    Supplier = apps.get_model('core', 'Supplier')
    SupplierPaymentRecord = apps.get_model('core', 'SupplierPaymentRecord')
    SupplierPaymentRecord.objects.filter(
        note='Opening payable carried over from existing purchase bills'
    ).delete()
    Supplier.objects.update(due=Decimal('0.00'))


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_supplier_due_supplierpaymentrecord'),
    ]

    operations = [
        migrations.RunPython(backfill_supplier_payables, unbackfill_supplier_payables),
    ]
