# Adds profit/category tracking, suppliers, and payment methods, and reconciles
# a pre-existing migration drift.
#
# NOTE: migrations 0003 and 0004 were recorded with empty/partial operations,
# while the live database already contains `core_invoice.invoice_type`,
# `core_invoiceitem.price` and the `core_stockrecord` table. Those three are
# therefore declared as *state-only* changes (SeparateDatabaseAndState with no
# database operations) so Django's recorded state matches the real schema
# without trying to re-create columns that already exist.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_invoice_invoice_type_invoiceitem_price_stockrecord'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # --- State-only reconciliation for the pre-existing drift ---
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='invoice',
                    name='invoice_type',
                    field=models.CharField(choices=[('sale', 'Sale'), ('purchase', 'Purchase')], max_length=20, null=True),
                ),
                migrations.AddField(
                    model_name='invoiceitem',
                    name='price',
                    field=models.DecimalField(decimal_places=2, max_digits=10, null=True),
                ),
                migrations.CreateModel(
                    name='StockRecord',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('qty', models.IntegerField(default=0)),
                        ('note', models.TextField(blank=True, null=True)),
                        ('stock_type', models.CharField(choices=[('sale', 'Sale'), ('purchase', 'Purchase')], max_length=20)),
                        ('date', models.DateTimeField(auto_now_add=True)),
                        ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_records', to='core.product')),
                        ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                    ],
                ),
            ],
        ),

        # --- Genuinely new schema ---
        migrations.AddField(
            model_name='product',
            name='cost_price',
            field=models.DecimalField(decimal_places=2, default=0.0, help_text='Your buying/purchase cost. Used to calculate profit.', max_digits=10),
        ),
        migrations.AddField(
            model_name='product',
            name='category',
            field=models.CharField(blank=True, help_text='e.g., Medicine, Surgical, Grocery', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='paymentrecord',
            name='payment_method',
            field=models.CharField(choices=[('cash', 'Cash'), ('bkash', 'bKash'), ('nagad', 'Nagad'), ('rocket', 'Rocket'), ('card', 'Card'), ('bank', 'Bank Transfer'), ('cheque', 'Cheque'), ('other', 'Other')], default='cash', max_length=20),
        ),
        migrations.CreateModel(
            name='Supplier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('phone', models.CharField(blank=True, max_length=20, null=True)),
                ('address', models.CharField(blank=True, max_length=220, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='invoice',
            name='supplier',
            field=models.ForeignKey(blank=True, help_text='Only used on purchase bills.', null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.supplier'),
        ),
    ]
