from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal

class CompanyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Pharmacy, Grocery, Electronics")
    description = models.TextField(blank=True, null=True, help_text="e.g., Wholesale local medicines and surgical tools.") 

    def __str__(self):
        return f"{self.user.username}'s Company Profile"

class Customer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=220)
    due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    def __str__(self):
        return self.name

class Product(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    qty = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                     help_text="Your buying/purchase cost. Used to calculate profit.")
    category = models.CharField(max_length=100, blank=True, null=True,
                                help_text="e.g., Medicine, Surgical, Grocery")

    @property
    def stock_value(self):
        return self.qty * self.price

    @property
    def margin_per_unit(self):
        return self.price - self.cost_price

    def __str__(self):
        return self.name


class Supplier(models.Model):
    """A vendor you buy stock from. Distinct from a Customer (who buys from you)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=220, blank=True, null=True)

    def __str__(self):
        return self.name

class StockRecord(models.Model):
    STOCK_TYPE = [
        ('sale', 'Sale'),
        ('purchase', 'Purchase')
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_records')
    qty = models.IntegerField(default=0)
    note = models.TextField(null=True, blank=True)
    stock_type = models.CharField(choices=STOCK_TYPE, max_length=20)
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is None:
            # New record
            if self.stock_type == 'purchase':
                self.product.qty += self.qty
            else: # sale
                self.product.qty -= self.qty
            self.product.save()
        else:
            # Update existing record
            try:
                old_record = StockRecord.objects.get(pk=self.pk)
                if old_record.product.pk != self.product.pk:
                    # Product changed
                    # Reverse on old
                    if old_record.stock_type == 'purchase':
                        old_record.product.qty -= old_record.qty
                    else:
                        old_record.product.qty += old_record.qty
                    old_record.product.save()
                    
                    # Apply on new
                    if self.stock_type == 'purchase':
                        self.product.qty += self.qty
                    else:
                        self.product.qty -= self.qty
                    self.product.save()
                else:
                    # Same product
                    # Reverse old effect
                    if old_record.stock_type == 'purchase':
                        self.product.qty -= old_record.qty
                    else:
                        self.product.qty += old_record.qty
                    
                    # Apply new effect
                    if self.stock_type == 'purchase':
                        self.product.qty += self.qty
                    else:
                        self.product.qty -= self.qty
                    self.product.save()
            except StockRecord.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Reverse effect before deleting
        if self.stock_type == 'purchase':
            self.product.qty -= self.qty
        else:
            self.product.qty += self.qty
        self.product.save()
        super().delete(*args, **kwargs)
        
    def __str__(self):
        return f"{self.product.name} / {self.stock_type} / {self.qty}"

class Invoice(models.Model):
    INVOICE_TYPE = [
        ('sale', 'Sale'),
        ('purchase', 'Purchase')
    ]
    DISCOUNT_TYPE = [
        ('percent', 'Percentage (%)'),
        ('fixed', 'Fixed Amount'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    invoice_type = models.CharField(choices=INVOICE_TYPE, max_length=20, null=True)
    customer = models.ForeignKey(Customer, null=True, on_delete=models.SET_NULL)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL,
                                 help_text="Only used on purchase bills.")
    total_value = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPE, default='percent',
                                     help_text="Whether discount_value is a percentage or a flat amount.")
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                         help_text="Percentage when discount_type is 'percent', otherwise a flat amount.")
    delivery_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'),
                                        help_text="Delivery / shipping charge added to the payable value.")
    payable_value = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_amount = models.DecimalField(max_digits=10, decimal_places=2)
    authorized_signature = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def discount_amount(self):
        """The discount actually applied, whether stored as a percent or a flat amount."""
        if self.discount_type == 'fixed':
            return self.discount_value
        return (self.total_value * self.discount_value / Decimal('100')).quantize(Decimal('0.01'))

    def __str__(self):
        return f"Invoice #{self.id}"

    def get_print_invoice_link(self):
        from django.urls import reverse
        return reverse('invoice_view', args=[self.id])

class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    
    def __str__(self):
        if self.product:
            return f"{self.product.name} ({self.quantity})"
        return f"Deleted Product ({self.quantity})"
    
class PaymentRecord(models.Model):
    TRANSACTION_TYPE = [
        ('charge', 'Charge / Added to Due'),
        ('payment', 'Payment Received')
    ]
    PAYMENT_METHOD = [
        ('cash', 'Cash'),
        ('bkash', 'bKash'),
        ('nagad', 'Nagad'),
        ('rocket', 'Rocket'),
        ('card', 'Card'),
        ('bank', 'Bank Transfer'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='ledger')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(choices=TRANSACTION_TYPE, max_length=20)
    payment_method = models.CharField(choices=PAYMENT_METHOD, max_length=20, default='cash')
    note = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk is None:
            # Automatically update the Customer's total due amount
            if self.transaction_type == 'charge':
                self.customer.due += self.amount
            elif self.transaction_type == 'payment':
                self.customer.due -= self.amount
            self.customer.save()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Safely reverse the balance if a record is deleted
        if self.transaction_type == 'charge':
            self.customer.due -= self.amount
        elif self.transaction_type == 'payment':
            self.customer.due += self.amount
        self.customer.save()
        super().delete(*args, **kwargs)
        
    def __str__(self):
        return f"{self.customer.name} - {self.transaction_type} - {self.amount}"