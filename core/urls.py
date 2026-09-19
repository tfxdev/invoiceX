from django.urls import path
from .views import *
from django.contrib import admin

urlpatterns = [
    # Landing page doubles as the sign-in page for anonymous visitors.
    path('', landing_view, name='landing'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard_view, name='home_dashboard'),
    path('dashboard/export/', dashboard_export_csv, name='dashboard_export_csv'),
    # API Endpoints (Used by Javascript)
    path('api/save_invoice/', save_invoice_api, name='save_invoice_api'),
    path('api/scan_invoice/', scan_invoice_api, name='scan_invoice_api'), # <-- Added the AI API endpoint
    path('profile/settings', profile_settings, name='dashboard'),
    path('invoices/', invoice_list_view, name='invoice_list'),
    path('invoice/<int:invoice_id>/', invoice_view, name='invoice_view'),
    path('create/', create_invoice_view, name='create_invoice'),
    path('invoice/<int:invoice_id>/edit/', edit_invoice_view, name='edit_invoice'), # <-- Add this line
    path('invoice/<int:invoice_id>/delete/', delete_invoice_view, name='delete_invoice'),
    # --- CUSTOMER MANAGEMENT ---
    path('customers/', customer_list_view, name='customer_list'),
    path('customer/<int:customer_id>/delete/', delete_customer_view, name='delete_customer'),
    path('products/', product_list_view, name='product_list'),
    # --- SUPPLIER MANAGEMENT ---
    path('suppliers/', supplier_list_view, name='supplier_list'),
    path('supplier/<int:supplier_id>/delete/', delete_supplier_view, name='delete_supplier'),
    path('api/supplier/<int:supplier_id>/ledger/', supplier_ledger_api, name='supplier_ledger_api'),
    path('product/<int:product_id>/delete/', delete_product_view, name='delete_product'),
    path('api/product/<int:product_id>/history/', product_stock_history_api, name='product_stock_history_api'),
    path('api/customer/<int:customer_id>/ledger/', customer_ledger_api, name='customer_ledger_api'),
    path('admin/', admin.site.urls),
]