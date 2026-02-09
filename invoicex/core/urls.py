from django.urls import path
from .views import invoice_view, create_invoice_view, save_invoice_api

urlpatterns = [
    path('invoice/<int:invoice_id>/', invoice_view, name='invoice_view'),
    path('create/', create_invoice_view, name='create_invoice'),
    path('api/save_invoice/', save_invoice_api, name='save_invoice_api'),
]