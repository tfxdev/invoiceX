from django.contrib import admin
from .models import Product, Invoice, InvoiceItem, Customer

admin.site.register(Product)
admin.site.register(Invoice)
admin.site.register(InvoiceItem)
admin.site.register(Customer)