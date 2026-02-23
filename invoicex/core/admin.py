from django.contrib import admin
from django.utils.html import format_html
from .models import Product, Invoice, InvoiceItem, Customer, CompanyProfile, StockRecord

class UserDataAdmin(admin.ModelAdmin):
    """A base admin class for models with a 'user' field."""
    
    def get_queryset(self, request):
        """Ensure users only see their own data."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(user=request.user)

    def save_model(self, request, obj, form, change):
        """Automatically assign the current user when creating an object."""
        if not obj.pk:
            obj.user = request.user
        super().save_model(request, obj, form, change)

class ProductAdmin(UserDataAdmin):
    list_display = ('name', 'qty', 'price')
    search_fields = ('name',)
    ordering = ('name',)
    
class CustomerAdmin(UserDataAdmin):
    list_display = ('name', 'phone', 'address', 'due')
    search_fields = ('name', 'phone')
    ordering = ('name',)

class InvoiceAdmin(UserDataAdmin):
    list_display = ('id', 'customer', 'total_value', 'due_amount', 'created_at', 'print_invoice_link')
    list_filter = ('created_at', 'customer')
    search_fields = ('customer__name', 'id')
    readonly_fields = ('print_invoice_link',)

    def print_invoice_link(self, obj):
        link = obj.get_print_invoice_link()
        return format_html(f'<a href="{link}" target="_blank">Print Invoice</a>')
    
    print_invoice_link.short_description = 'Print'

class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company_name', 'email', 'phone')

class StockRecordAdmin(UserDataAdmin):
    list_display = ('product', 'qty', 'stock_type', 'date')
    list_filter = ('stock_type', 'date')
    search_fields = ('product__name',)

admin.site.register(Product, ProductAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(CompanyProfile, CompanyProfileAdmin)
admin.site.register(StockRecord, StockRecordAdmin)
