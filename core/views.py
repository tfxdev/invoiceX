from urllib import request

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
from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
import csv
from django.http import HttpResponse
import difflib
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

    today = timezone.localdate()

    # ---- Date range for the trend charts (7 / 30 / 90 days) ----
    try:
        range_days = int(request.GET.get('range', 30))
    except (TypeError, ValueError):
        range_days = 30
    if range_days not in (7, 30, 90):
        range_days = 30
    range_start = today - timedelta(days=range_days - 1)

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
    today_revenue = sales.filter(created_at__date=today).aggregate(Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')

    # 7. Purchases (goods bought in)
    purchases = Invoice.objects.filter(user=request.user, invoice_type='purchase')
    total_purchase = purchases.aggregate(Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')

    # 8. This month's revenue
    month_revenue = sales.filter(created_at__date__gte=today.replace(day=1)).aggregate(
        Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')

    # 9. Average invoice value
    avg_invoice_value = (total_revenue / total_invoices_count) if total_invoices_count else Decimal('0.00')

    # 10. Contacts and inventory value
    total_customers = Customer.objects.filter(user=request.user).count()
    total_products = Product.objects.filter(user=request.user).count()
    inventory_value = Product.objects.filter(user=request.user).aggregate(
        v=Sum(ExpressionWrapper(F('qty') * F('price'),
                                output_field=DecimalField(max_digits=14, decimal_places=2)))
    )['v'] or Decimal('0.00')

    # 11. Collections vs outstanding on sale invoices
    paid_collected = sales.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
    invoice_outstanding = sales.aggregate(Sum('due_amount'))['due_amount__sum'] or Decimal('0.00')

    # 12. Payables (money you still owe suppliers)
    total_payable = purchases.aggregate(Sum('due_amount'))['due_amount__sum'] or Decimal('0.00')

    # ---- Range-scoped querysets -------------------------------------------
    sales_in_range = sales.filter(created_at__date__gte=range_start)
    purchases_in_range = purchases.filter(created_at__date__gte=range_start)
    items_in_range = InvoiceItem.objects.filter(
        invoice__user=request.user,
        invoice__invoice_type='sale',
        invoice__created_at__date__gte=range_start,
    )
    range_revenue = sales_in_range.aggregate(Sum('payable_value'))['payable_value__sum'] or Decimal('0.00')
    range_orders = sales_in_range.count()

    # ---- Profit (selling price - cost price) ------------------------------
    # NOTE: uses the product's *current* cost_price, so historic invoices are
    # valued at today's cost. Good enough for a dashboard trend.
    unit_profit = ExpressionWrapper(
        (Coalesce(F('price'), Value(Decimal('0.00'))) - Coalesce(F('product__cost_price'), Value(Decimal('0.00'))))
        * F('quantity'),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )

    def sum_profit(queryset):
        return queryset.aggregate(p=Sum(unit_profit))['p'] or Decimal('0.00')

    gross_profit_total = sum_profit(InvoiceItem.objects.filter(
        invoice__user=request.user, invoice__invoice_type='sale'))
    gross_profit_range = sum_profit(items_in_range)
    profit_margin = (gross_profit_total / total_revenue * 100) if total_revenue else Decimal('0.00')
    costs_missing = Product.objects.filter(user=request.user, cost_price=0).count()

    # ---- Chart data --------------------------------------------------------
    # a) Revenue / profit trend across the selected range
    day_list = [range_start + timedelta(days=i) for i in range(range_days)]

    def daily_series(queryset, field='payable_value'):
        rows = (queryset.filter(created_at__date__gte=range_start)
                .values('created_at__date')
                .annotate(total=Sum(field)))
        bucket = {row['created_at__date']: float(row['total'] or 0) for row in rows}
        return [round(bucket.get(day, 0.0), 2) for day in day_list]

    trend_labels = [day.strftime('%b %d') for day in day_list]
    trend_sales = daily_series(sales)
    trend_purchases = daily_series(purchases)

    profit_rows = (items_in_range.values('invoice__created_at__date')
                   .annotate(p=Sum(unit_profit)))
    profit_bucket = {row['invoice__created_at__date']: float(row['p'] or 0) for row in profit_rows}
    trend_profit = [round(profit_bucket.get(day, 0.0), 2) for day in day_list]

    # b) Top selling products by quantity (in range)
    top_products = list(
        items_in_range.values('product__name')
        .annotate(qty=Sum('quantity'), revenue=Sum('subtotal'))
        .order_by('-qty')[:6]
    )
    top_product_labels = [(row['product__name'] or 'Deleted product') for row in top_products]
    top_product_qty = [int(row['qty'] or 0) for row in top_products]

    # c) Highest customer balances
    top_debtors = list(
        Customer.objects.filter(user=request.user, due__gt=0).order_by('-due')[:5]
    )

    # d) Sales by category (in range)
    cat_rows = list(
        items_in_range.values('product__category')
        .annotate(total=Sum('subtotal'))
        .order_by('-total')[:8]
    )
    category_labels = [(row['product__category'] or 'Uncategorised') for row in cat_rows]
    category_values = [round(float(row['total'] or 0), 2) for row in cat_rows]

    # e) Receivables aging buckets (all-time snapshot)
    aging_buckets = [0.0, 0.0, 0.0, 0.0]
    for inv in sales.filter(due_amount__gt=0).only('due_amount', 'created_at'):
        age = (today - timezone.localtime(inv.created_at).date()).days
        idx = 0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3
        aging_buckets[idx] += float(inv.due_amount or 0)
    aging_buckets = [round(v, 2) for v in aging_buckets]

    # f) Peak trading hours (in range)
    hour_rows = (sales_in_range.values('created_at__hour')
                 .annotate(total=Sum('payable_value')))
    hour_map = {row['created_at__hour']: float(row['total'] or 0) for row in hour_rows}
    peak_hours = [round(hour_map.get(h, 0.0), 2) for h in range(24)]

    # g) Cash flow: money in vs money out (in range)
    ledger_in = PaymentRecord.objects.filter(
        user=request.user, transaction_type='payment',
        date__date__gte=range_start).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    invoice_in = sales_in_range.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
    cash_in = float(invoice_in) + float(ledger_in)
    cash_out = float(purchases_in_range.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00'))

    # h) Payment methods used (in range)
    method_rows = list(
        PaymentRecord.objects.filter(user=request.user, transaction_type='payment',
                                     date__date__gte=range_start)
        .values('payment_method').annotate(total=Sum('amount')).order_by('-total')
    )
    method_display = dict(PaymentRecord.PAYMENT_METHOD)
    method_labels = [method_display.get(row['payment_method'], row['payment_method']) for row in method_rows]
    method_values = [round(float(row['total'] or 0), 2) for row in method_rows]

    # i) Supplier spend + payables (in range)
    supplier_rows = list(
        purchases_in_range.filter(supplier__isnull=False)
        .values('supplier__name').annotate(total=Sum('payable_value')).order_by('-total')[:6]
    )
    supplier_labels = [row['supplier__name'] for row in supplier_rows]
    supplier_values = [round(float(row['total'] or 0), 2) for row in supplier_rows]
    top_payables = list(
        purchases.filter(supplier__isnull=False, due_amount__gt=0)
        .values('supplier__name').annotate(due=Sum('due_amount')).order_by('-due')[:5]
    )

    # j) Inventory turnover: units sold vs stock on hand (in range)
    turnover_rows = list(
        items_in_range.values('product__name', 'product__qty')
        .annotate(sold=Sum('quantity')).order_by('-sold')[:6]
    )
    turnover_labels = [(row['product__name'] or 'Deleted product') for row in turnover_rows]
    turnover_sold = [int(row['sold'] or 0) for row in turnover_rows]
    turnover_stock = [int(row['product__qty'] or 0) for row in turnover_rows]

    # k) Dead stock: in stock but no sales in the range
    sold_product_ids = items_in_range.exclude(product__isnull=True).values_list('product_id', flat=True)
    dead_stock_qs = Product.objects.filter(user=request.user, qty__gt=0).exclude(id__in=sold_product_ids)
    dead_stock_count = dead_stock_qs.count()
    dead_stock_products = list(dead_stock_qs.order_by('-qty')[:5])

    context = {
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'total_invoices_count': total_invoices_count,
        'total_due': total_due,
        'low_stock_count': low_stock_count,
        'low_stock_products': low_stock_products,
        'recent_invoices': recent_invoices,
        'total_purchase': total_purchase,
        'month_revenue': month_revenue,
        'avg_invoice_value': avg_invoice_value,
        'total_customers': total_customers,
        'total_products': total_products,
        'inventory_value': inventory_value,
        'top_debtors': top_debtors,
        'total_payable': total_payable,
        'top_payables': top_payables,
        'gross_profit_total': gross_profit_total,
        'gross_profit_range': gross_profit_range,
        'profit_margin': profit_margin,
        'costs_missing': costs_missing,
        'range_revenue': range_revenue,
        'range_orders': range_orders,
        'range_days': range_days,
        'dead_stock_count': dead_stock_count,
        'dead_stock_products': dead_stock_products,
        'cash_in': cash_in,
        'cash_out': cash_out,
        'chart_data': {
            'trend_labels': trend_labels,
            'trend_sales': trend_sales,
            'trend_purchases': trend_purchases,
            'trend_profit': trend_profit,
            'type_labels': ['Sales', 'Purchases'],
            'type_values': [float(total_revenue), float(total_purchase)],
            'product_labels': top_product_labels,
            'product_qty': top_product_qty,
            'payment_labels': ['Collected', 'Outstanding'],
            'payment_values': [float(paid_collected), float(invoice_outstanding)],
            'category_labels': category_labels,
            'category_values': category_values,
            'aging_labels': ['0-30 days', '31-60 days', '61-90 days', '90+ days'],
            'aging_values': aging_buckets,
            'peak_hours': peak_hours,
            'cash_labels': ['Money In', 'Money Out'],
            'cash_values': [cash_in, cash_out],
            'method_labels': method_labels,
            'method_values': method_values,
            'supplier_labels': supplier_labels,
            'supplier_values': supplier_values,
            'turnover_labels': turnover_labels,
            'turnover_sold': turnover_sold,
            'turnover_stock': turnover_stock,
        },
    }

    return render(request, 'dashboard.html', context)


@login_required
def dashboard_export_csv(request):
    """Downloads the invoice ledger for the selected range as a CSV file."""
    today = timezone.localdate()
    try:
        range_days = int(request.GET.get('range', 30))
    except (TypeError, ValueError):
        range_days = 30
    if range_days not in (7, 30, 90):
        range_days = 30
    range_start = today - timedelta(days=range_days - 1)

    invoices = (Invoice.objects
                .filter(user=request.user, created_at__date__gte=range_start)
                .select_related('customer', 'supplier')
                .order_by('-created_at'))

    unit_profit = ExpressionWrapper(
        (Coalesce(F('price'), Value(Decimal('0.00'))) - Coalesce(F('product__cost_price'), Value(Decimal('0.00'))))
        * F('quantity'),
        output_field=DecimalField(max_digits=16, decimal_places=2),
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="dashboard_{range_days}d_{today.isoformat()}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(['Invoice #', 'Date', 'Type', 'Party', 'Items',
                     'Total', 'Discount', 'Delivery', 'Payable', 'Paid', 'Due', 'Est. Profit'])

    for inv in invoices:
        if inv.invoice_type == 'purchase':
            party = (inv.supplier.name if inv.supplier
                     else inv.customer.name if inv.customer else '')
            profit = ''
        else:
            party = inv.customer.name if inv.customer else 'Walk-in'
            profit = inv.items.aggregate(p=Sum(unit_profit))['p'] or Decimal('0.00')

        writer.writerow([
            inv.id,
            timezone.localtime(inv.created_at).strftime('%Y-%m-%d %H:%M'),
            inv.invoice_type,
            party,
            inv.items.count(),
            f'{inv.total_value:.2f}',
            (f'{inv.discount_value:.2f}%' if inv.discount_type == 'percent'
             else f'{inv.discount_value:.2f}'),
            f'{inv.delivery_cost:.2f}',
            f'{inv.payable_value:.2f}',
            f'{inv.paid_amount:.2f}',
            f'{inv.due_amount:.2f}',
            f'{profit:.2f}' if profit != '' else '',
        ])

    return response


@login_required
def product_list_view(request):
    """Handles displaying, adding, editing, and restocking products."""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            Product.objects.create(
                user=request.user,
                name=request.POST.get('name', ''),
                price=Decimal(request.POST.get('price', 0) or 0),
                cost_price=Decimal(request.POST.get('cost_price', 0) or 0),
                category=(request.POST.get('category') or '').strip() or None,
                qty=int(request.POST.get('qty', 0) or 0)
            )
            
        elif action == 'edit':
            product_id = request.POST.get('product_id')
            product = get_object_or_404(Product, id=product_id, user=request.user)
            product.name = request.POST.get('name', '')
            product.price = Decimal(request.POST.get('price', 0) or 0)
            product.cost_price = Decimal(request.POST.get('cost_price', 0) or 0)
            product.category = (request.POST.get('category') or '').strip() or None
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
    categories = (Product.objects.filter(user=request.user)
                  .exclude(category__isnull=True).exclude(category='')
                  .values_list('category', flat=True).distinct().order_by('category'))
    return render(request, 'product_list.html', {'products': products, 'categories': categories})

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
                payment_method=request.POST.get('payment_method', 'cash'),
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
            'method': r.get_payment_method_display(),
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
def supplier_list_view(request):
    """Handles displaying, adding and editing suppliers (vendors you buy from)."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            Supplier.objects.create(
                user=request.user,
                name=request.POST.get('name', ''),
                phone=request.POST.get('phone', ''),
                address=request.POST.get('address', '')
            )
        elif action == 'edit':
            supplier = get_object_or_404(Supplier, id=request.POST.get('supplier_id'), user=request.user)
            supplier.name = request.POST.get('name', '')
            supplier.phone = request.POST.get('phone', '')
            supplier.address = request.POST.get('address', '')
            supplier.save()

        return redirect('supplier_list')

    suppliers = Supplier.objects.filter(user=request.user).order_by('name')

    # Purchase spend per supplier, so the page is useful at a glance
    spend_rows = (Invoice.objects
                  .filter(user=request.user, invoice_type='purchase', supplier__isnull=False)
                  .values('supplier_id')
                  .annotate(total=Sum('payable_value'), bills=Count('id'), outstanding=Sum('due_amount')))
    spend_map = {row['supplier_id']: row for row in spend_rows}
    for s in suppliers:
        row = spend_map.get(s.id, {})
        s.total_spend = row.get('total') or Decimal('0.00')
        s.bill_count = row.get('bills') or 0
        s.outstanding = row.get('outstanding') or Decimal('0.00')

    return render(request, 'supplier_list.html', {'suppliers': suppliers})

@login_required
def delete_supplier_view(request, supplier_id):
    """Securely deletes a supplier."""
    if request.method == 'POST':
        supplier = get_object_or_404(Supplier, id=supplier_id, user=request.user)
        supplier.delete()
    return redirect('supplier_list')

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
    items = invoice.items.all().order_by('product__name')
    return render(request, 'invoice.html', {'invoice': invoice, 'items':items, 'company_profile': company_profile})


@login_required
def create_invoice_view(request):
    """View for creating a new invoice/POS screen"""
    products = list(Product.objects.filter(user=request.user).values('id', 'name', 'price', 'qty'))
    for p in products:
            p['price'] = float(p['price'])
    customers = Customer.objects.filter(user=request.user)
    suppliers = Supplier.objects.filter(user=request.user)
    
    return render(request, 'create_invoice.html', {
        'products_json': json.dumps(products), 
        'customers': customers,
        'suppliers': suppliers,
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
    suppliers = Supplier.objects.filter(user=request.user)
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
        'supplier_id': invoice.supplier.id if invoice.supplier else "",
        'discount_type': invoice.discount_type,
        'discount_value': float(invoice.discount_value),
        'delivery_cost': float(invoice.delivery_cost),
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
        'suppliers': suppliers,
        'existing_invoice': json.dumps(invoice_data) # Passes edit data to JS
    })


def _invoice_discount_fields(data):
    """Normalise the discount/delivery payload for an Invoice.

    Accepts the legacy ``discount_percent`` key so older clients (and the
    AI-scanner payload) keep working.
    """
    discount_type = data.get('discount_type') or 'percent'
    if discount_type not in dict(Invoice.DISCOUNT_TYPE):
        discount_type = 'percent'

    def as_decimal(value):
        return Decimal(str(0 if value in (None, '') else value))

    return {
        'discount_type': discount_type,
        'discount_value': as_decimal(data.get('discount_value', data.get('discount_percent', 0))),
        'delivery_cost': as_decimal(data.get('delivery_cost', 0)),
    }


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
            supplier = None
            if invoice_type == 'purchase':
                # Purchase bills are addressed to a SUPPLIER, not a customer.
                if customer_id:
                    if str(customer_id).isdigit():
                        supplier = get_object_or_404(Supplier, id=customer_id, user=request.user)
                    else:
                        supplier, created = Supplier.objects.get_or_create(
                            user=request.user,
                            name=str(customer_id),
                            defaults={'phone': 'N/A', 'address': 'N/A'}
                        )
            elif customer_id:
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
                discount_fields = _invoice_discount_fields(data)
                invoice.invoice_type = invoice_type
                invoice.customer = customer
                invoice.supplier = supplier
                invoice.total_value = Decimal(data['total_value'])
                invoice.discount_type = discount_fields['discount_type']
                invoice.discount_value = discount_fields['discount_value']
                invoice.delivery_cost = discount_fields['delivery_cost']
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
                    supplier=supplier,
                    total_value=Decimal(data['total_value']),
                    payable_value=Decimal(data['payable_value']),
                    paid_amount=Decimal(data['paid_amount']),
                    due_amount=Decimal(data['due_amount']),
                    authorized_signature=data.get('authorized_signature', ''),
                    **_invoice_discount_fields(data)
                )
                if customer and invoice_type == 'sale':
                    due_amount = Decimal(data['due_amount'])
                    customer.due += due_amount
                    customer.save()
                    
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
            # We are inside the @transaction.atomic block; without this the partial
            # invoice/customer writes would be committed alongside the error reply.
            transaction.set_rollback(True)
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
        
        try:
            profile = CompanyProfile.objects.get(user=request.user)
            industry_str = f"This business is a {profile.industry}." if profile.industry else ""
            desc_str = f"They specialize in: {profile.description}." if profile.description else ""
            location_str = f"They are located at: {profile.address}." if profile.address else ""
        except CompanyProfile.DoesNotExist:
            industry_str = desc_str = location_str = ""

        # --- NEW: LEXICON INJECTION (The Cheat Sheet) ---
        # Get all product names for this specific user. 
        # (We limit to 2000 to keep the AI lightning fast, which covers 99% of small businesses)
        db_product_names = list(Product.objects.filter(user=request.user).values_list('name', flat=True)[:2000])
        lexicon_string = "\n".join([f"- {name}" for name in db_product_names])

        # 2. Inject it dynamically into the Prompt
        prompt = f"""You are an expert invoice data extractor.

        BUSINESS CONTEXT:
        {industry_str}
        {location_str}
        {desc_str}

        VALID PRODUCT DICTIONARY:
        {lexicon_string}

        CRITICAL INSTRUCTIONS:
        1. DICTIONARY GROUNDING: You MUST use the "VALID PRODUCT DICTIONARY" above as your primary reference. When you read a handwritten item, before making a guess, check if it resembles any item in the dictionary. If it is a visual match (even if spelled poorly on the paper), output the EXACT name as it appears in the dictionary.
        2. RESOLVING DITTO MARKS: Customers frequently use ditto marks (") or the word "DO" / "Do." to refer to the product name on the line directly above it. You MUST resolve this visually. NEVER output '"' or 'DO' as a product name. You must combine the previous name with the new extension.
        3. NO HALLUCINATION: Only output items that are actually on the invoice. If an item is clearly not in the dictionary, output what you see, but prioritize dictionary matches heavily.

        I am providing you with one or more images of an invoice (it may be multiple pages of the same bill).
        Combine all the items across all pages into a single, unified JSON object.
        Do not duplicate items. 

        The JSON must follow this exact schema:
        {{
        "invoice_type": "sale" or "purchase",
        "customer_name": "<string or null>",
        "authorized_signature": "<string or null>",
        "discount_percent": <number>,
        "paid_amount": <number>,
        "items": [
            {{
            "product_name": "<string>",
            "quantity": <integer>,
            "price": <number>,
            "subtotal": <number>
            }}
        ]
        }}

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

        # ── Superior Fuzzy Matching against DB products ──
        db_products = list(Product.objects.filter(user=request.user).values('id', 'name', 'price', 'qty'))

        def best_match(extracted_name):
            extracted_name_lower = extracted_name.lower().strip()
            best_p = None
            highest_ratio = 0.0

            for p in db_products:
                db_name_lower = p['name'].lower().strip()
                
                # 1. Exact Match
                if extracted_name_lower == db_name_lower:
                    return p
                
                # 2. Substring Match (e.g. "Napa" inside "Napa Extra 500mg")
                if extracted_name_lower in db_name_lower or db_name_lower in extracted_name_lower:
                    return p
                    
                # 3. Mathematical Fuzzy Match (Catches spelling mistakes like "Paracetamal")
                ratio = difflib.SequenceMatcher(None, extracted_name_lower, db_name_lower).ratio()
                if ratio > highest_ratio:
                    highest_ratio = ratio
                    best_p = p

            # If the best fuzzy match is at least 65% similar, we accept it as a match!
            if highest_ratio > 0.65:
                return best_p
                
            return None

        matched_items = []
        for item in extracted.get('items', []):
            match = best_match(item['product_name'])
            
            if match:
                # STRICT DB OVERRIDE: Throw away the AI's hallucination. 
                # Use the exact Name and Price from your database.
                final_name = match['name']
                final_price = float(match['price'])
                final_subtotal = item['quantity'] * final_price
            else:
                # No match found. Keep the AI's guess so it shows up 
                # in the yellow "Unresolved" warning box for manual fixing.
                final_name = item['product_name']
                final_price = item.get('price', 0)
                final_subtotal = item.get('subtotal', 0)

            matched_items.append({
                'product_name':  final_name,
                'product_id':    match['id'] if match else None,
                'product_price': final_price,
                'stock_qty':     match['qty'] if match else None,
                'quantity':      item['quantity'],
                'price':         final_price,
                'subtotal':      final_subtotal,
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