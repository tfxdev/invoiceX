from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json
from decimal import Decimal

from .models import Invoice, Product, Customer, InvoiceItem, CompanyProfile, StockRecord
from .forms import *

def custom_404_view(request, exception=None):
    """Redirect all 404 errors to the create invoice page."""
    return HttpResponseRedirect(reverse('create_invoice'))

@login_required
def invoice_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if invoice.user != request.user:
        raise Http404
    
    try:
        company_profile = CompanyProfile.objects.get(user=request.user)
    except CompanyProfile.DoesNotExist:
        company_profile = None # Handle case where user has no company profile

    return render(request, 'invoice.html', {'invoice': invoice, 'company_profile': company_profile})

@login_required
def create_invoice_view(request):
    products = Product.objects.filter(user=request.user)
    customers = Customer.objects.filter(user=request.user)
    return render(request, 'create_invoice.html', {'products': products, 'customers': customers})

@csrf_exempt
@login_required
def save_invoice_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            customer_id = data.get('customer_id')
            customer = None
            if customer_id:
                # Ensure the customer belongs to the current user
                customer = get_object_or_404(Customer, id=customer_id, user=request.user)

            # Create the invoice and assign it to the current user
            invoice = Invoice.objects.create(
                user=request.user,
                invoice_type=data['invoice_type'],
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
                # Ensure the product belongs to the current user
                product = get_object_or_404(Product, id=item_data['product_id'], user=request.user)
                quantity_sold = int(item_data['quantity'])
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity_sold,
                    price=Decimal(item_data['price']),
                    subtotal=Decimal(item_data['subtotal'])
                )

                # Update product quantity
                if data['invoice_type'] == 'sale':
                    product.qty -= quantity_sold
                    StockRecord.objects.create(
                            user=request.user,
                            product=product,
                            qty=quantity_sold,
                            stock_type=data['invoice_type'],
                        )
                elif data['invoice_type'] == 'purchase':
                    product.qty += quantity_sold
                    StockRecord.objects.create(
                            user=request.user,
                            product=product,
                            qty=quantity_sold,
                            stock_type=data['invoice_type'],
                        )
                product.save()
            
            return JsonResponse({'status': 'success', 'invoice_id': invoice.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


def profile_settings(request):
    company_profile = get_object_or_404(CompanyProfile, user=request.user)
    user_account = get_object_or_404(User, username = request.user.username)
    
    if request.method == 'POST':
        company_profile_form = CompanyProfileForm(request.POST, instance=company_profile)
        user_account_form = AccountForm(request.POST, instance=user_account)

        if company_profile_form.is_valid() and user_account_form.is_valid():
            company_profile_form.save()
            user_account_form.save()
            return redirect(profile_settings)
    else:
        cp_form = CompanyProfileForm(instance=company_profile)
        ua_form = AccountForm(instance=user_account)
    context = {
        'company_profile_form': cp_form,
        'user_account_form': ua_form
    }
    return render(request, 'profile_settings.html', context)