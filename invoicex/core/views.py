from django.shortcuts import render
from .models import Invoice

def invoice_view(request, invoice_id):
    invoice = Invoice.objects.get(id=invoice_id)
    return render(request, 'invoice.html', {'invoice': invoice})