from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds discount mode (% vs fixed) and delivery charge.

    ``discount_percent`` is renamed to ``discount_value`` rather than dropped and
    re-added, so existing rows keep their stored percentage. ``discount_type``
    defaults to 'percent', which is exactly what those existing values meant.
    """

    dependencies = [
        ('core', '0005_profit_categories_suppliers_payment_methods'),
    ]

    operations = [
        migrations.RenameField(
            model_name='invoice',
            old_name='discount_percent',
            new_name='discount_value',
        ),
        migrations.AddField(
            model_name='invoice',
            name='discount_type',
            field=models.CharField(
                choices=[('percent', 'Percentage (%)'), ('fixed', 'Fixed Amount')],
                default='percent',
                help_text='Whether discount_value is a percentage or a flat amount.',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='invoice',
            name='delivery_cost',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                help_text='Delivery / shipping charge added to the payable value.',
                max_digits=10,
            ),
        ),
    ]
