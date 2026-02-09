from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from decimal import Decimal

from .models import Invoice, Product, Customer, InvoiceItem

def invoice_view(request, invoice_id):
    invoice = Invoice.objects.get(id=invoice_id)
    return render(request, 'invoice.html', {'invoice': invoice})

def create_invoice_view(request):
    products = Product.objects.all()
    customers = Customer.objects.all()
    return render(request, 'create_invoice.html', {'products': products, 'customers': customers})

@csrf_exempt
def save_invoice_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            customer_id = data.get('customer_id')
            customer = None
            if customer_id:
                customer = Customer.objects.get(id=customer_id)

            invoice = Invoice.objects.create(
                customer=customer,
                total_value=Decimal(data['total_value']),
                discount_percent=Decimal(data['discount_percent']),
                payable_value=Decimal(data['payable_value']),
                paid_amount=Decimal(data['paid_amount']),
                due_amount=Decimal(data['due_amount']),
                authorized_signature=data.get('authorized_signature', '')
            )
            
            # Create InvoiceItems and update product quantities
            for item_data in data['items']:
                product = Product.objects.get(id=item_data['product_id'])
                quantity_sold = int(item_data['quantity'])
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity_sold,
                    subtotal=Decimal(item_data['subtotal'])
                )
                
                # Update product quantity
                product.qty -= quantity_sold
                product.save()
            
            return JsonResponse({'status': 'success', 'invoice_id': invoice.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)
