from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Invoice, InvoiceItem, Customer

class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'total_value', 'due_amount', 'created_at', 'print_invoice_link')
    list_filter = ('created_at', 'customer')
    search_fields = ('customer__name', 'id')
    readonly_fields = ('print_invoice_link',)

    def print_invoice_link(self, obj):
        return format_html(f'<a href="{obj.get_print_invoice_link()}" target="_blank">Print Invoice</a>')
    
    print_invoice_link.short_description = 'Print'

admin.site.register(Product)
admin.site.register(Customer)
admin.site.register(InvoiceItem)
admin.site.register(Invoice, InvoiceAdmin)
