from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseRedirect, Http404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth.models import User
from django.conf import settings
import json
import base64
from decimal import Decimal
import google.generativeai as genai
from django.db.models import Sum, Count, Q
from django.utils import timezone

from .models import *
from .forms import CompanyProfileForm, AccountForm

# Configure AI SDK at module level to prevent re-initializing on every request
genai.configure(api_key=settings.GEMINI_API_KEY)


def custom_404_view(request, exception=None):
    """Redirect all 404 errors to the create invoice page."""
    return HttpResponseRedirect(reverse('create_invoice'))

@login_required
def dashboard_view(request):
    """The main command center / dashboard."""
    
    # 1. Total Revenue (Sales only)
    sales = Invoice.objects.filter(user=request.user, invoice_type='sale')
    total_revenue = sales.aggregate(Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')
    
    # 2. Total Invoices Generated
    total_invoices_count = sales.count()
    
    # 3. Total Due from Customers (Market Outstanding)
    total_due = Customer.objects.filter(user=request.user).aggregate(Sum('due'))['due__sum'] or Decimal('0.00')
    
    # 4. Low Stock Alerts (Products with 5 or fewer items)
    low_stock_count = Product.objects.filter(user=request.user, qty__lte=5).count()
    low_stock_products = Product.objects.filter(user=request.user, qty__lte=5).order_by('qty')[:6]
    
    # 5. Recent Activity
    recent_invoices = Invoice.objects.filter(user=request.user).order_by('-created_at')[:6]
    
    # 6. Today's Revenue
    today = timezone.now().date()
    today_revenue = sales.filter(created_at__date=today).aggregate(Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')

    context = {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'total_invoices_count': total_invoices_count,
        'total_due': total_due,
        'low_stock_count': low_stock_count,
        'low_stock_products': low_stock_products,
        'recent_invoices': recent_invoices,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def product_list_view(request):
    """Handles displaying, adding, editing, and restocking products."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            Product.objects.create(
                user=request.user,
                name=request.POST.get('name', ''),
                price=Decimal(request.POST.get('price', 0)),
                qty=int(request.POST.get('qty', 0))
            )
            
        elif action == 'edit':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id, user=request.user)
            product.name = request.POST.get('name', '')
            product.price = Decimal(request.POST.get('price', 0))
            # Note: We don't edit QTY here. We use 'adjust_stock' for safe tracking.
            product.save()
            
        elif action == 'adjust_stock':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id, user=request.user)
            adj_type = request.POST.get('adj_type') # 'add' or 'reduce'
            adj_qty = int(request.POST.get('adj_qty', 0))
            note = request.POST.get('note', 'Manual Adjustment')

            # Map the adjustment to your existing StockRecord logic
            stock_type = 'purchase' if adj_type == 'add' else 'sale'
            
            # Creating this record automatically updates product.qty via your model's save() method
            StockRecord.objects.create(
                user=request.user,
                product=product,
                qty=adj_qty,
                stock_type=stock_type,
                note=note
            )
            
        return redirect('product_list')

    # Fetch all products, order alphabetically
    products = Product.objects.filter(user=request.user).order_by('name')
    return render(request, 'product_list.html', {'products': products})

@login_required
def delete_product_view(request, product_id):
    """Securely deletes a product."""
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id, user=request.user)
        product.delete()
    return redirect('product_list')

@login_required
def product_stock_history_api(request, product_id):
    """Returns the stock movement history for a specific product."""
    product = get_object_or_404(Product, id=product_id, user=request.user)
    
    # Grab the 50 most recent stock changes
    records = StockRecord.objects.filter(product=product).order_by('-date')[:50]
    
    history_data = []
    for r in records:
        history_data.append({
            'date': r.date.strftime("%b %d, %Y - %I:%M %p"),
            'type': r.stock_type,  # 'purchase' (Added) or 'sale' (Deducted)
            'qty': r.qty,
            'note': r.note or "System Update"
        })
        
    return JsonResponse({
        'status': 'success', 
        'product_name': product.name, 
        'history': history_data
    })
    
@login_required
def customer_list_view(request):
    """Handles displaying, adding, editing, and receiving payments for customers."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            Customer.objects.create(
                user=request.user,
                name=request.POST.get('name', ''),
                phone=request.POST.get('phone', ''),
                address=request.POST.get('address', ''),
                due=Decimal(request.POST.get('due', 0) or 0)
            )
        elif action == 'edit':
            customer_id = request.POST.get('customer_id')
            customer = get_object_or_404(Customer, id=customer_id, user=request.user)
            customer.name = request.POST.get('name', '')
            customer.phone = request.POST.get('phone', '')
            customer.address = request.POST.get('address', '')
            # We don't edit the due amount directly here anymore. We use the ledger!
            customer.save()
            
        elif action == 'adjust_balance':
            # --- NEW: Handles Payments & Charges ---
            customer_id = request.POST.get('customer_id')
            customer = get_object_or_404(Customer, id=customer_id, user=request.user)
            trans_type = request.POST.get('trans_type') # 'payment' or 'charge'
            amount = Decimal(request.POST.get('amount', 0))
            note = request.POST.get('note', 'Manual Adjustment')

            PaymentRecord.objects.create(
                user=request.user,
                customer=customer,
                amount=amount,
                transaction_type=trans_type,
                note=note
            )
            
        return redirect('customer_list')

    customers = Customer.objects.filter(user=request.user).order_by('name')
    return render(request, 'customer_list.html', {'customers': customers})

@login_required
def customer_ledger_api(request, customer_id):
    """Returns the payment and charge history for a specific customer."""
    customer = get_object_or_404(Customer, id=customer_id, user=request.user)
    
    # Grab the 50 most recent ledger entries
    records = PaymentRecord.objects.filter(customer=customer).order_by('-date')[:50]
    
    history_data = []
    for r in records:
        history_data.append({
            'date': r.date.strftime("%b %d, %Y - %I:%M %p"),
            'type': r.transaction_type,  # 'payment' or 'charge'
            'amount': float(r.amount),
            'note': r.note or "System Update"
        })
        
    return JsonResponse({
        'status': 'success', 
        'customer_name': customer.name, 
        'current_due': float(customer.due),
        'history': history_data
    })

@login_required
def delete_customer_view(request, customer_id):
    """Securely deletes a customer."""
    if request.method == 'POST':
        customer = get_object_or_404(Customer, id=customer_id, user=request.user)
        customer.delete()
    return redirect('customer_list')

@login_required
def invoice_list_view(request):
    """Displays a list of all invoices for the user."""
    # Fetch all invoices, newest first
    invoices = Invoice.objects.filter(user=request.user).order_by('-created_at')
    
    return render(request, 'invoice_list.html', {
        'invoices': invoices
    })
    
@login_required
def invoice_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if invoice.user != request.user:
        raise Http404
    
    try:
        company_profile = CompanyProfile.objects.get(user=request.user)
    except CompanyProfile.DoesNotExist:
        company_profile = None

    return render(request, 'invoice.html', {'invoice': invoice, 'company_profile': company_profile})


@login_required
def create_invoice_view(request):
    """View for creating a new invoice/POS screen"""
    products = list(Product.objects.filter(user=request.user).values('id', 'name', 'price', 'qty'))
    for p in products:
            p['price'] = float(p['price'])
    customers = Customer.objects.filter(user=request.user)
    
    return render(request, 'create_invoice.html', {
        'products_json': json.dumps(products), 
        'customers': customers,
        'existing_invoice': 'null' # Indicates we are creating, not editing
    })
@login_required
@transaction.atomic
def delete_invoice_view(request, invoice_id):
    """Securely deletes an invoice and refunds the inventory."""
    if request.method == 'POST':
        invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
        
        # Reverse the stock for all items on this invoice
        for item in invoice.items.all():
            if item.product:
                reversal_type = 'purchase' if invoice.invoice_type == 'sale' else 'sale'
                StockRecord.objects.create(
                    user=request.user,
                    product=item.product,
                    qty=item.quantity,
                    stock_type=reversal_type,
                    note=f"Stock reversal for deleted Invoice #{invoice.id}"
                )
        
        # Delete the invoice (Django automatically deletes the attached InvoiceItems)
        invoice.delete()
        
    return redirect('invoice_list')

@login_required
def edit_invoice_view(request, invoice_id):
    """View for editing an existing invoice"""
    invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
    customers = Customer.objects.filter(user=request.user)
    products = list(Product.objects.filter(user=request.user).values('id', 'name', 'price', 'qty'))
    
    # CRITICAL UI FIX: Adjust the baseline stock for the frontend JS.
    # Since these items are already deducted in the DB, we temporarily add them 
    # back to the JS product list so the frontend math doesn't double-deduct them while editing.
    for item in invoice.items.all():
        for p in products:
            p['price'] = float(p['price'])
            if item.product and p['id'] == item.product.id:
                if invoice.invoice_type == 'sale':
                    p['qty'] += item.quantity
                else:
                    p['qty'] -= item.quantity

    # Package the existing invoice data for the Javascript UI
    invoice_data = {
        'id': invoice.id,
        'invoice_type': invoice.invoice_type,
        'customer_id': invoice.customer.id if invoice.customer else "",
        'discount_percent': float(invoice.discount_percent),
        'paid_amount': float(invoice.paid_amount),
        'items': [
            {
                'product_id': item.product.id if item.product else None,
                'name': item.product.name if item.product else "Deleted Product",
                'price': float(item.price),
                'quantity': item.quantity,
            } for item in invoice.items.all()
        ]
    }

    return render(request, 'create_invoice.html', {
        'products_json': json.dumps(products), 
        'customers': customers,
        'existing_invoice': json.dumps(invoice_data) # Passes edit data to JS
    })


@login_required
@transaction.atomic
def save_invoice_api(request):
    """Handles saving NEW invoices and updating EDITED invoices."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            invoice_type = data['invoice_type']
            invoice_id = data.get('invoice_id') # Present if editing
            
            customer_id = data.get('customer_id')
            customer = None
            if customer_id:
                # If the frontend sends a pure number, it's an existing customer
                if str(customer_id).isdigit():
                    customer = get_object_or_404(Customer, id=customer_id, user=request.user)
                else:
                    # If the frontend sends a string name, AUTO-CREATE the new customer!
                    customer, created = Customer.objects.get_or_create(
                        user=request.user,
                        name=str(customer_id),
                        defaults={'phone': 'N/A', 'address': 'N/A'}
                    )

            if invoice_id:
                # --- UPDATE EXISTING INVOICE ---
                invoice = get_object_or_404(Invoice, id=invoice_id, user=request.user)
                
                # 1. Reverse the stock for all OLD items
                for old_item in invoice.items.all():
                    if old_item.product:
                        reversal_type = 'purchase' if invoice.invoice_type == 'sale' else 'sale'
                        StockRecord.objects.create(
                            user=request.user,
                            product=old_item.product,
                            qty=old_item.quantity,
                            stock_type=reversal_type,
                            note=f"Stock reversal for editing Invoice #{invoice.id}"
                        )
                
                # 2. Delete old items
                invoice.items.all().delete()
                
                # 3. Update Invoice metadata
                invoice.invoice_type = invoice_type
                invoice.customer = customer
                invoice.total_value = Decimal(data['total_value'])
                invoice.discount_percent = Decimal(data['discount_percent'])
                invoice.payable_value = Decimal(data['payable_value'])
                invoice.paid_amount = Decimal(data['paid_amount'])
                invoice.due_amount = Decimal(data['due_amount'])
                invoice.authorized_signature = data.get('authorized_signature', '')
                invoice.save()
                
            else:
                # --- CREATE NEW INVOICE ---
                invoice = Invoice.objects.create(
                    user=request.user,
                    invoice_type=invoice_type,
                    customer=customer,
                    total_value=Decimal(data['total_value']),
                    discount_percent=Decimal(data['discount_percent']),
                    payable_value=Decimal(data['payable_value']),
                    paid_amount=Decimal(data['paid_amount']),
                    due_amount=Decimal(data['due_amount']),
                    authorized_signature=data.get('authorized_signature', '')
                )
            
            # Create the NEW items and NEW stock records (runs for both Create & Edit)
            for item_data in data['items']:
                product = get_object_or_404(Product, id=item_data['product_id'], user=request.user)
                quantity_sold = int(item_data['quantity'])
                
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity_sold,
                    price=Decimal(item_data['price']),
                    subtotal=Decimal(item_data['subtotal'])
                )

                # The custom save() method in models.py handles updating product.qty
                StockRecord.objects.create(
                    user=request.user,
                    product=product,
                    qty=quantity_sold,
                    stock_type=invoice_type,
                    note=f"Applied via Invoice #{invoice.id}"
                )
            
            return JsonResponse({'status': 'success', 'invoice_id': invoice.id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@login_required
def scan_invoice_api(request):
    """Handles multi-image uploads, calls Gemini AI, and aggregates results."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body)
        images = data.get('images', [])

        if not images:
            return JsonResponse({'status': 'error', 'message': 'No images provided.'}, status=400)

        model = genai.GenerativeModel('gemini-3.1-flash-lite')

        prompt = """You are an expert invoice data extractor.
I am providing you with one or more images of an invoice (it may be multiple pages of the same bill).
Combine all the items across all pages into a single, unified JSON object.
Do not duplicate items. 

The JSON must follow this exact schema:
{
  "invoice_type": "sale" or "purchase",
  "customer_name": "<string or null>",
  "authorized_signature": "<string or null>",
  "discount_percent": <number>,
  "paid_amount": <number>,
  "items": [
    {
      "product_name": "<string>",
      "quantity": <integer>,
      "price": <number>,
      "subtotal": <number>
    }
  ]
}
Rules:
- invoice_type: use "sale" when goods go OUT (customer invoice), "purchase" when goods come IN (supplier bill).
- discount_percent: percentage value (e.g. 10 for 10%). Default 0 if not present.
- paid_amount: the amount already paid. Default to the full payable amount if not stated.
- All monetary values must be plain numbers, no currency symbols.
- If a field cannot be found, use null for strings or 0 for numbers.
"""

        gemini_content = [prompt]
        for img in images:
            gemini_content.append({
                'mime_type': img.get('media_type', 'image/jpeg'),
                'data': base64.b64decode(img.get('data', ''))
            })

        response = model.generate_content(
            gemini_content,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            )
        )
        
        extracted = json.loads(response.text)

        # ── Fuzzy Matching against DB products ──
        db_products = list(Product.objects.filter(user=request.user).values('id', 'name', 'price', 'qty'))

        def best_match(name):
            name_lower = name.lower()
            for p in db_products:
                if p['name'].lower() == name_lower:
                    return p
            for p in db_products:
                if name_lower in p['name'].lower() or p['name'].lower() in name_lower:
                    return p
            return None

        matched_items = []
        for item in extracted.get('items', []):
            match = best_match(item['product_name'])
            matched_items.append({
                'product_name':  item['product_name'],
                'product_id':    match['id']    if match else None,
                'product_price': float(match['price']) if match else item['price'],
                'stock_qty':     match['qty']   if match else None,
                'quantity':      item['quantity'],
                'price':         item['price'],
                'subtotal':      item['subtotal'],
                'matched':       match is not None,
            })

        # ── Aggregation Logic (Merge identical products) ──
        aggregated_items = {}
        for item in matched_items:
            # Group by DB product ID, or by the raw extracted name if it's not in the DB
            key = item['product_id'] if item['product_id'] else item['product_name'].lower()
            
            if key in aggregated_items:
                aggregated_items[key]['quantity'] += item['quantity']
                aggregated_items[key]['subtotal'] = aggregated_items[key]['quantity'] * aggregated_items[key]['price']
            else:
                aggregated_items[key] = item
                
        final_items = list(aggregated_items.values())

        # ── Match Customer Name ──
        customer_name = extracted.get('customer_name') or ''
        db_customers  = list(Customer.objects.filter(user=request.user).values('id', 'name'))
        matched_customer = None
        if customer_name:
            cn_lower = customer_name.lower()
            for c in db_customers:
                if c['name'].lower() == cn_lower or cn_lower in c['name'].lower():
                    matched_customer = c
                    break

        response_data = {  
            'status':               'success',
            'invoice_type':         extracted.get('invoice_type', 'sale'),
            'customer_name':        customer_name,
            'customer_id':          matched_customer['id'] if matched_customer else None,
            'authorized_signature': extracted.get('authorized_signature', ''),
            'discount_percent':     extracted.get('discount_percent', 0),
            'paid_amount':          extracted.get('paid_amount', 0),
            'items':                final_items,
        }
        print(response_data)

        return JsonResponse({
            'status':               'success',
            'invoice_type':         extracted.get('invoice_type', 'sale'),
            'customer_name':        customer_name,
            'customer_id':          matched_customer['id'] if matched_customer else None,
            'authorized_signature': extracted.get('authorized_signature', ''),
            'discount_percent':     extracted.get('discount_percent', 0),
            'paid_amount':          extracted.get('paid_amount', 0),
            'items':                final_items,
        })

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'AI returned invalid JSON. Please try again.'}, status=500)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def profile_settings(request):
    """User profile and settings view."""
    company_profile, created = CompanyProfile.objects.get_or_create(user=request.user)
    user_account = get_object_or_404(User, username=request.user.username)
    
    if request.method == 'POST':
        cp_form = CompanyProfileForm(request.POST, instance=company_profile)
        ua_form = AccountForm(request.POST, instance=user_account)

        if cp_form.is_valid() and ua_form.is_valid():
            cp_form.save()
            
            # Correctly hash the password if changed
            user = ua_form.save(commit=False)
            raw_password = ua_form.cleaned_data.get('password')
            if raw_password:
                user.set_password(raw_password)
            user.save()
            
            return redirect('dashboard')
    else:
        cp_form = CompanyProfileForm(instance=company_profile)
        ua_form = AccountForm(instance=user_account)
        # Clear out the password field on load so the user doesn't see a hash string
        ua_form.initial['password'] = ''

    context = {
        'company_profile_form': cp_form,
        'user_account_form': ua_form
    }
    return render(request, 'profile_settings.html', context)