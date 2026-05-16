# core/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, F, Min, Q
from django.db.models.functions import TruncMonth, Coalesce
from django.db import transaction
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from datetime import timedelta, datetime, date
from decimal import Decimal
from functools import wraps
import csv
import pandas as pd

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    Expense, Branch, Production, Product, Sale,
    Customer, Truck, TripLog, InventoryLog,User, StockPurchase
)
from .forms import (
    ExpenseForm, ProductionForm, SaleForm,
    SaleItemFormSet, TripLogForm, StockPurchaseForm
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def role_required(*roles):
    """Restrict a view to users whose role is in `roles`."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, 'You do not have permission to access that page.')
                if request.user.role == 'clerk':
                    return redirect('clerk_dashboard')
                return redirect('home')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def get_branch_filter(user):
    """Return branch to filter by, or None if user sees all branches."""
    if user.role in ['admin', 'owner']:
        return None
    return user.branch


# ─── Home / Dashboard ────────────────────────────────────────────────────────

@login_required
def home(request):
    """Route users to the correct dashboard based on role."""
    if request.user.role == 'clerk':
        return redirect('clerk_dashboard')
    return redirect('main_dashboard')


@login_required
def clerk_dashboard(request):
    """Simple task-focused dashboard for clerks."""
    today = timezone.now().date()
    branch = request.user.branch

    today_sales = Sale.objects.filter(
        sale_date=today, branch=branch
    ).aggregate(total=Sum('total_amount'))['total'] or 0

    today_expenses = Expense.objects.filter(
        date=today, branch=branch
    ).aggregate(total=Sum('amount'))['total'] or 0

    low_stock = Product.objects.filter(
        branch=branch,
        current_stock__lte=F('min_threshold'),
        is_active=True
    ).select_related('branch')

    recent_sales = Sale.objects.filter(
        branch=branch
    ).order_by('-sale_date')[:5]

    return render(request, 'core/clerk_dashboard.html', {
        'title': f'Dashboard — {branch.name if branch else ""}',
        'today_sales': today_sales,
        'today_expenses': today_expenses,
        'low_stock': low_stock,
        'recent_sales': recent_sales,
        'today': today,
    })


@login_required
def main_dashboard(request):
    """Full dashboard for admin, owner, branch_manager."""
    today = timezone.now().date()
    branch = get_branch_filter(request.user)

    # Base querysets filtered by branch
    sales_qs = Sale.objects.all()
    expenses_qs = Expense.objects.all()
    production_qs = Production.objects.all()
    products_qs = Product.objects.filter(is_active=True)
    customers_qs = Customer.objects.all()
    trucks_qs = Truck.objects.all()

    if branch:
        sales_qs = sales_qs.filter(branch=branch)
        expenses_qs = expenses_qs.filter(branch=branch)
        production_qs = production_qs.filter(branch=branch)
        products_qs = products_qs.filter(branch=branch)
        customers_qs = customers_qs.filter(branch=branch)
        trucks_qs = trucks_qs.filter(branch=branch)

    # Today's KPIs
    today_sales = sales_qs.filter(sale_date=today).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0')
    today_expenses = expenses_qs.filter(date=today).aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    today_production = production_qs.filter(production_date=today).aggregate(
        total=Sum('quantity'))['total'] or Decimal('0')

    # This month
    month_start = today.replace(day=1)
    month_sales = sales_qs.filter(sale_date__gte=month_start).aggregate(
        total=Sum('total_amount'))['total'] or Decimal('0')
    month_expenses = expenses_qs.filter(date__gte=month_start).aggregate(
        total=Sum('amount'))['total'] or Decimal('0')
    month_profit = month_sales - month_expenses

    # Alerts
    low_stock = products_qs.filter(
        current_stock__lte=F('min_threshold')
    ).order_by('current_stock')
    overdue_count = customers_qs.filter(balance_owed__gt=0).count()
    overdue_amount = customers_qs.filter(balance_owed__gt=0).aggregate(
        total=Sum('balance_owed'))['total'] or Decimal('0')

    # Truck summary
    truck_profit = Decimal('0')
    total_km = 0
    for truck in trucks_qs:
        income = sales_qs.filter(truck=truck).aggregate(
            total=Sum('amount_paid'))['total'] or Decimal('0')
        t_expenses = expenses_qs.filter(truck=truck).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        truck_profit += (income - t_expenses)
        total_km += TripLog.objects.filter(truck=truck).aggregate(
            total=Sum('distance_km'))['total'] or 0

    # Monthly sales chart
    monthly_sales = (
        sales_qs
        .annotate(month=TruncMonth('sale_date'))
        .values('month')
        .annotate(total=Sum('total_amount'))
        .order_by('month')
    )
    sales_labels = [e['month'].strftime('%b %Y') for e in monthly_sales]
    sales_data = [float(e['total'] or 0) for e in monthly_sales]

    # Monthly expenses chart
    monthly_expenses = (
        expenses_qs
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )
    expenses_labels = [e['month'].strftime('%b %Y') for e in monthly_expenses]
    expenses_data = [float(e['total'] or 0) for e in monthly_expenses]

    return render(request, 'core/dashboard.html', {
        'title': 'Dashboard',
        'today': today,
        'branch': branch,
        'today_sales': today_sales,
        'today_expenses': today_expenses,
        'today_production': today_production,
        'month_sales': month_sales,
        'month_expenses': month_expenses,
        'month_profit': month_profit,
        'low_stock': low_stock,
        'overdue_customers': overdue_count,
        'overdue_amount': overdue_amount,
        'truck_summary': {'total_profit': truck_profit, 'total_km': total_km},
        'sales_labels': sales_labels,
        'sales_data': sales_data,
        'expenses_labels': expenses_labels,
        'expenses_data': expenses_data,
    })


# ─── Sales ───────────────────────────────────────────────────────────────────

@login_required
def sale_create(request):
    if request.method == 'POST':
        sale_form = SaleForm(request.POST, user=request.user)
        item_formset = SaleItemFormSet(request.POST, prefix='items')

        if sale_form.is_valid() and item_formset.is_valid():
            try:
                with transaction.atomic():
                    sale = sale_form.save(commit=False)
                    if request.user.role in ['admin', 'owner']:
                        if not sale.branch:
                            messages.error(request, 'Please select a branch.')
                            raise ValidationError('Branch required')
                    else:
                        if not request.user.branch:
                            messages.error(request, 'Your account has no branch assigned.')
                            raise ValidationError('No branch')
                        sale.branch = request.user.branch

                    sale.total_amount = Decimal('0')
                    sale.created_by = request.user
                    sale.save()

                    for item_form in item_formset:
                        if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                            item = item_form.save(commit=False)
                            item.sale = sale
                            item.total_price = item.quantity * item.unit_price
                            sale.total_amount += item.total_price

                            product = item.product
                            if product.current_stock < item.quantity:
                                raise ValidationError(f'Insufficient stock for {product.name}')

                            stock_before = product.current_stock
                            Product.objects.filter(id=product.id).update(
                                current_stock=F('current_stock') - item.quantity
                            )
                            item.save()
                            InventoryLog.objects.create(
                                product=product,
                                branch=sale.branch,
                                movement_type='sale',
                                quantity=-item.quantity,
                                stock_before=stock_before,
                                stock_after=stock_before - item.quantity,
                                reference_note=f'Sale #{sale.id}',
                                created_by=request.user,
                            )

                    sale.created_by = request.user
                    sale.save()

                    balance_due = sale.total_amount - sale.amount_paid
                    if balance_due > 0 and sale.customer:
                        sale.customer.balance_owed += balance_due
                        sale.customer.save()
                    messages.success(request, 'Sale recorded successfully!')
                    return redirect('sale_list')

            except ValidationError as e:
                messages.error(request, str(e))
    else:
        sale_form = SaleForm(user=request.user)
        item_formset = SaleItemFormSet(prefix='items')

    if request.user.role not in ['admin', 'owner'] and request.user.branch:
        sale_form.fields['customer'].queryset = Customer.objects.filter(
            branch=request.user.branch)

    return render(request, 'core/sale_form.html', {
        'sale_form': sale_form,
        'item_formset': item_formset,
        'title': 'Record New Sale',
    })


@login_required
def sale_list(request):
    sales = Sale.objects.all().order_by('-sale_date')
    return render(request, 'core/sale_list.html', {
        'sales': sales,
        'title': 'Sales Records',
    })


@login_required
def sale_detail(request, sale_id):
    sale = get_object_or_404(Sale, id=sale_id)
    if request.user.role not in ['admin', 'owner'] and sale.branch != request.user.branch:
        raise PermissionDenied('You do not have access to this sale.')
    items = sale.items.all()
    balance_due = sale.total_amount - sale.amount_paid
    return render(request, 'core/sale_detail.html', {
        'sale': sale,
        'items': items,
        'balance_due': balance_due,
        'title': f'Sale #{sale.id} — {sale.sale_date}',
    })


# ─── Customers ───────────────────────────────────────────────────────────────

@login_required
def customer_list(request):
    branch = get_branch_filter(request.user)
    customers = Customer.objects.all()
    if branch:
        customers = customers.filter(branch=branch)
    return render(request, 'core/customer_list.html', {
        'customers': customers.order_by('name'),
        'title': 'Customers',
    })


@login_required
def customer_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        credit_limit = request.POST.get('credit_limit', '0').strip()
        if not name:
            messages.error(request, 'Customer name is required.')
        else:
            try:
                if request.user.role not in ['admin', 'owner']:
                    branch = request.user.branch
                else:
                    branch = Branch.objects.get(id=request.POST.get('branch'))
                Customer.objects.create(
                    branch=branch,
                    name=name,
                    phone=phone,
                    credit_limit=Decimal(credit_limit or '0'),
                )
                messages.success(request, f'Customer {name} added.')
                return redirect('customer_list')
            except Exception as e:
                messages.error(request, str(e))

    branches = Branch.objects.filter(status='active') if request.user.role in ['admin', 'owner'] else None
    return render(request, 'core/customer_create.html', {
        'title': 'Add New Customer',
        'branches': branches,
    })


@login_required
def overdue_customers(request):
    branch = get_branch_filter(request.user)
    customers = Customer.objects.filter(balance_owed__gt=0)
    if branch:
        customers = customers.filter(branch=branch)

    customers = customers.annotate(
        oldest_unpaid=Coalesce(
            Min('sales__sale_date',
                filter=Q(sales__payment_status__in=['credit', 'partial'])),
            timezone.now().date() - timedelta(days=1)
        )
    ).order_by('oldest_unpaid', '-balance_owed')

    today = timezone.now().date()
    for cust in customers:
        cust.days_overdue = (today - cust.oldest_unpaid).days if cust.oldest_unpaid else 0
        if cust.days_overdue > 60:
            cust.alert_level = 'danger'
            cust.alert_text = f'Very overdue ({cust.days_overdue} days)'
        elif cust.days_overdue > 30:
            cust.alert_level = 'warning'
            cust.alert_text = f'Overdue ({cust.days_overdue} days)'
        else:
            cust.alert_level = 'secondary'
            cust.alert_text = f'Mildly overdue ({cust.days_overdue} days)'

    total_overdue = customers.aggregate(total=Sum('balance_owed'))['total'] or Decimal('0')
    return render(request, 'core/overdue_customers.html', {
        'customers': customers,
        'total_overdue': total_overdue,
        'title': 'Overdue Customers',
    })


@login_required
def customer_repayment(request, customer_id):
    customer = get_object_or_404(Customer, id=customer_id)
    if request.user.role not in ['admin', 'owner'] and customer.branch != request.user.branch:
        raise PermissionDenied('You do not have access to this customer.')

    if request.method == 'POST':
        amount_str = request.POST.get('amount', '').strip()
        payment_method = request.POST.get('payment_method', '').strip()
        notes = request.POST.get('notes', '').strip()
        try:
            amount = Decimal(amount_str)
            if amount <= 0:
                raise ValueError('Amount must be greater than zero.')
            if amount > customer.balance_owed:
                raise ValueError(f'Amount exceeds balance owed ({customer.balance_owed} TZS).')
            with transaction.atomic():
                # Apply repayment to oldest unpaid sales first
                remaining = amount
                unpaid_sales = customer.sales.filter(
                    payment_status__in=['credit', 'partial']
                ).order_by('sale_date')

                for sale in unpaid_sales:
                    if remaining <= 0:
                        break
                    outstanding = sale.total_amount - sale.amount_paid
                    payment = min(remaining, outstanding)
                    sale.amount_paid += payment
                    sale.save()  # triggers payment_status update via Sale.save()
                    remaining -= payment

                customer.balance_owed -= amount
                customer.save()

                messages.success(
                    request,
                    f'Repayment of {amount:,.0f} TZS recorded for {customer.name}. '
                    f'Remaining balance: {customer.balance_owed:,.0f} TZS.'
                )
                return redirect('overdue_customers')
        except (ValueError, Exception) as e:
            messages.error(request, str(e))

    return render(request, 'core/customer_repayment.html', {
        'customer': customer,
        'title': f'Record Repayment — {customer.name}',
    })


# ─── Inventory & Production ──────────────────────────────────────────────────

@login_required
def stock_purchase(request):
    if request.method == 'POST':
        form = StockPurchaseForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product = form.cleaned_data['product']
                    quantity = form.cleaned_data['quantity']
                    cost_per_unit = form.cleaned_data.get('cost_per_unit')
                    supplier = form.cleaned_data.get('supplier_name') or 'Unknown'
                    date = form.cleaned_data['date']
                    notes = form.cleaned_data.get('notes', '')

                    stock_before = product.current_stock
                    Product.objects.filter(id=product.id).update(
                        current_stock=F('current_stock') + quantity
                    )
                    if cost_per_unit:
                        Product.objects.filter(id=product.id).update(cost_price=cost_per_unit)

                    InventoryLog.objects.create(
                        product=product,
                        branch=product.branch,
                        movement_type='purchase',
                        quantity=quantity,
                        stock_before=stock_before,
                        stock_after=stock_before + quantity,
                        reference_note=f'Purchase from {supplier}',
                        created_by=request.user,
                    )

                    if cost_per_unit:
                        Expense.objects.create(
                            branch=product.branch,
                            category='raw_materials',
                            amount=cost_per_unit * quantity,
                            description=f'Purchase: {quantity} {product.unit} of {product.name} from {supplier}. {notes}',
                            date=date,
                            created_by=request.user,
                        )

                    messages.success(request, f'Stock updated! {quantity} {product.unit} of {product.name} added.')
                    return redirect('stock_purchase')
            except Exception as e:
                messages.error(request, f'Error: {str(e)}')
    else:
        form = StockPurchaseForm(user=request.user)

    recent_logs = InventoryLog.objects.filter(
        movement_type='purchase'
    ).select_related('product', 'branch').order_by('-created_at')[:20]

    return render(request, 'core/stock_purchase.html', {
        'form': form,
        'recent_logs': recent_logs,
        'title': 'Stock Purchase / Intake',
    })


@login_required
def production_list(request):
    productions = Production.objects.all().order_by('-production_date')
    return render(request, 'core/production_list.html', {
        'productions': productions,
        'title': 'Production Records',
    })


@login_required
def production_create(request):
    if request.method == 'POST':
        form = ProductionForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    production = form.save(commit=False)
                    if request.user.role not in ['admin', 'owner']:
                        production.branch = request.user.branch
                    else:
                        production.branch = production.product.branch

                    recipe = production.product.get_production_recipe()
                    if not recipe:
                        raise ValidationError('No production recipe defined for this product.')

                    for raw_id, qty_per_unit in recipe.items():
                        raw_product = get_object_or_404(Product, id=raw_id, branch=production.branch)
                        required = qty_per_unit * production.quantity
                        if raw_product.current_stock < required:
                            raise ValidationError(
                                f'Insufficient {raw_product.name}. '
                                f'Available: {raw_product.current_stock}, Needed: {required}'
                            )
                        stock_before = raw_product.current_stock
                        Product.objects.filter(id=raw_product.id).update(
                            current_stock=F('current_stock') - required
                        )
                        InventoryLog.objects.create(
                            product=raw_product,
                            branch=production.branch,
                            movement_type='production_out',
                            quantity=-required,
                            stock_before=stock_before,
                            stock_after=stock_before - required,
                            reference_note=f'Production — {production.product.name}',
                            created_by=request.user,
                        )

                    finished = Product.objects.get(id=production.product.id)
                    stock_before_finished = finished.current_stock
                    Product.objects.filter(id=production.product.id).update(
                        current_stock=F('current_stock') + production.quantity
                    )
                    production.raw_materials_consumed = {
                        str(rid): float(qty_per_unit * production.quantity)
                        for rid, qty_per_unit in recipe.items()
                    }
                    production.save()
                    InventoryLog.objects.create(
                        product=finished,
                        branch=production.branch,
                        movement_type='production_in',
                        quantity=production.quantity,
                        stock_before=stock_before_finished,
                        stock_after=stock_before_finished + production.quantity,
                        reference_note=f'Production #{production.id}',
                        created_by=request.user,
                    )

                    messages.success(request, 'Production recorded! Raw materials deducted.')
                    return redirect('production_list')
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = ProductionForm(user=request.user)

    return render(request, 'core/production_form.html', {
        'form': form,
        'title': 'Record New Production',
    })


# ─── Expenses ────────────────────────────────────────────────────────────────

@login_required
def expense_list(request):
    branch = get_branch_filter(request.user)
    expenses = Expense.objects.all().order_by('-date')
    if branch:
        expenses = expenses.filter(branch=branch)

    today = timezone.now().date()
    return render(request, 'core/expense_list.html', {
        'expenses': expenses,
        'title': 'Expenses',
        'total_all': expenses.aggregate(total=Sum('amount'))['total'] or 0,
        'total_today': expenses.filter(date=today).aggregate(total=Sum('amount'))['total'] or 0,
        'total_month': expenses.filter(date__gte=today.replace(day=1)).aggregate(total=Sum('amount'))['total'] or 0,
        'total_week': expenses.filter(date__gte=today - timedelta(days=7)).aggregate(total=Sum('amount'))['total'] or 0,
    })


@login_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            if request.user.role in ['admin', 'owner']:
                if not expense.branch:
                    messages.error(request, 'Please select a branch.')
                    return render(request, 'core/expense_form.html', {'form': form, 'title': 'Add Expense'})
            else:
                if not request.user.branch:
                    messages.error(request, 'Your account has no branch assigned.')
                    return render(request, 'core/expense_form.html', {'form': form, 'title': 'Add Expense'})
                expense.branch = request.user.branch
            expense.save()
            messages.success(request, 'Expense added successfully!')
            return redirect('expense_list')
    else:
        form = ExpenseForm()

    if request.user.role not in ['admin', 'owner'] and request.user.branch:
        form.fields['branch'].queryset = Branch.objects.filter(id=request.user.branch.id)
        form.fields['branch'].initial = request.user.branch
        form.fields['branch'].widget.attrs['readonly'] = True
        form.fields['branch'].required = False

    return render(request, 'core/expense_form.html', {
        'form': form,
        'title': 'Add New Expense',
    })


# ─── Fleet ───────────────────────────────────────────────────────────────────

@login_required
def truck_list(request):
    branch = get_branch_filter(request.user)
    trucks = Truck.objects.all()
    if branch:
        trucks = trucks.filter(branch=branch)
    return render(request, 'core/truck_list.html', {
        'trucks': trucks,
        'title': 'Trucks Overview',
    })


@login_required
def truck_profitability(request, truck_id=None):
    branch = get_branch_filter(request.user)
    trucks = Truck.objects.all()
    if branch:
        trucks = trucks.filter(branch=branch)

    selected_truck = profitability = maintenance_alert = None

    if truck_id:
        selected_truck = get_object_or_404(Truck, id=truck_id)
        if branch and selected_truck.branch != branch:
            raise PermissionDenied()

        sales_income = Sale.objects.filter(truck=selected_truck).aggregate(
            total=Sum('amount_paid'))['total'] or Decimal('0')
        expenses = Expense.objects.filter(truck=selected_truck).aggregate(
            total=Sum('amount'))['total'] or Decimal('0')
        trips = TripLog.objects.filter(truck=selected_truck)
        total_km = trips.aggregate(total=Sum('distance_km'))['total'] or 0
        total_fuel = trips.aggregate(total=Sum('fuel_used'))['total'] or Decimal('0')

        profitability = {
            'income': sales_income,
            'expenses': expenses,
            'profit': sales_income - expenses,
            'total_km': total_km,
            'total_fuel': total_fuel,
            'cost_per_km': expenses / Decimal(total_km) if total_km > 0 else Decimal('0'),
            'fuel_per_km': total_fuel / Decimal(total_km) if total_km > 0 else Decimal('0'),
        }

        if selected_truck.last_maintenance_date:
            months_since = (timezone.now().date() - selected_truck.last_maintenance_date).days // 30
            if months_since >= 6:
                maintenance_alert = (
                    f'Maintenance overdue! Last service: {selected_truck.last_maintenance_date} '
                    f'({months_since} months ago).'
                )

    return render(request, 'core/truck_profitability.html', {
        'trucks': trucks,
        'selected_truck': selected_truck,
        'profitability': profitability,
        'maintenance_alert': maintenance_alert,
        'title': 'Truck Profitability',
    })


@login_required
def trip_create(request):
    initial = {}
    truck_id = request.GET.get('truck')
    if truck_id:
        initial['truck'] = truck_id

    if request.method == 'POST':
        form = TripLogForm(request.POST)
        if form.is_valid():
            trip = form.save()
            if trip.end_odometer:
                trip.truck.current_odometer = trip.end_odometer
                trip.truck.save()
            messages.success(request, 'Trip logged successfully!')
            return redirect('truck_profit_detail', truck_id=trip.truck.id)
    else:
        form = TripLogForm(initial=initial)

    if request.user.role not in ['admin', 'owner'] and request.user.branch:
        form.fields['truck'].queryset = Truck.objects.filter(branch=request.user.branch)
        form.fields['sale'].queryset = Sale.objects.filter(branch=request.user.branch)

    return render(request, 'core/trip_form.html', {
        'form': form,
        'title': 'Log New Trip',
    })


# ─── Reports ─────────────────────────────────────────────────────────────────

@role_required('admin', 'owner', 'branch_manager')
def sales_report(request):
    year = request.GET.get('year', timezone.now().year)
    export = request.GET.get('export')
    branch = get_branch_filter(request.user)

    sales = Sale.objects.filter(sale_date__year=year)
    if branch:
        sales = sales.filter(branch=branch)

    monthly_sales = sales.annotate(month=TruncMonth('sale_date')).values('month').annotate(
        total=Sum('total_amount'), paid=Sum('amount_paid')
    ).order_by('month')

    for m in monthly_sales:
        m['outstanding'] = (m['total'] - m['paid']) if m['total'] and m['paid'] else Decimal('0')

    by_method = sales.values('payment_method').annotate(total=Sum('total_amount')).order_by('payment_method')
    grand_total = sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    total_paid = sales.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0')
    outstanding_credit = sales.filter(payment_status__in=['credit', 'partial']).aggregate(
        total=Sum('total_amount') - Sum('amount_paid')
    )['total'] or Decimal('0')

    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="Sales_Report_{year}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Sales Report', f'Year: {year}'])
        writer.writerow(['Month', 'Total (TZS)', 'Paid (TZS)', 'Outstanding (TZS)'])
        for m in monthly_sales:
            writer.writerow([m['month'].strftime('%B %Y'), m['total'] or 0, m['paid'] or 0, m['outstanding']])
        writer.writerow(['Grand Total', grand_total, total_paid, outstanding_credit])
        return response

    return render(request, 'core/sales_report.html', {
        'year': year, 'monthly_sales': monthly_sales, 'by_method': by_method,
        'grand_total': grand_total, 'total_paid': total_paid,
        'outstanding_credit': outstanding_credit, 'branch': branch,
        'title': f'Sales Report — {year}',
    })


@role_required('admin', 'owner', 'branch_manager')
def tra_expense_report(request):
    year = request.GET.get('year', timezone.now().year)
    export = request.GET.get('export')
    branch = get_branch_filter(request.user)

    expenses = Expense.objects.filter(date__year=year)
    if branch:
        expenses = expenses.filter(branch=branch)

    category_totals = expenses.values('category').annotate(total=Sum('amount')).order_by('category')
    monthly = expenses.annotate(month=TruncMonth('date')).values('month').annotate(
        total=Sum('amount')).order_by('month')
    grand_total = expenses.aggregate(total=Sum('amount'))['total'] or 0

    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="TRA_Expenses_{year}.csv"'
        writer = csv.writer(response)
        writer.writerow(['Category', 'Total (TZS)'])
        for cat in category_totals:
            writer.writerow([cat['category'], cat['total'] or 0])
        writer.writerow([])
        writer.writerow(['Month', 'Total (TZS)'])
        for m in monthly:
            writer.writerow([m['month'].strftime('%B %Y'), m['total'] or 0])
        writer.writerow(['Grand Total', grand_total])
        return response

    return render(request, 'core/tra_report.html', {
        'year': year, 'category_totals': category_totals,
        'monthly_breakdown': monthly, 'grand_total': grand_total,
        'branch': branch, 'title': f'TRA Expense Report — {year}',
    })


@role_required('admin', 'owner', 'branch_manager')
def profit_and_loss(request):
    year = int(request.GET.get('year', timezone.now().year))
    month = request.GET.get('month', '')
    export = request.GET.get('export')
    branch = get_branch_filter(request.user)

    sales_qs = Sale.objects.filter(sale_date__year=year)
    expenses_qs = Expense.objects.filter(date__year=year)
    if month:
        sales_qs = sales_qs.filter(sale_date__month=month)
        expenses_qs = expenses_qs.filter(date__month=month)
    if branch:
        sales_qs = sales_qs.filter(branch=branch)
        expenses_qs = expenses_qs.filter(branch=branch)

    months_map = {
        1: 'January', 2: 'February', 3: 'March', 4: 'April',
        5: 'May', 6: 'June', 7: 'July', 8: 'August',
        9: 'September', 10: 'October', 11: 'November', 12: 'December'
    }

    sales_data = list(sales_qs.values('sale_date__month', 'branch__name').annotate(
        revenue=Sum('total_amount'), collected=Sum('amount_paid')))
    expense_data = list(expenses_qs.values('date__month', 'category').annotate(total=Sum('amount')))

    if sales_data:
        df_sales = pd.DataFrame(sales_data)
        monthly_revenue = df_sales.groupby('sale_date__month').agg(
            revenue=('revenue', 'sum'), collected=('collected', 'sum')).reset_index()
    else:
        monthly_revenue = pd.DataFrame(columns=['sale_date__month', 'revenue', 'collected'])

    if expense_data:
        df_expenses = pd.DataFrame(expense_data)
        monthly_expenses = df_expenses.groupby('date__month').agg(
            total_expenses=('total', 'sum')).reset_index()
    else:
        monthly_expenses = pd.DataFrame(columns=['date__month', 'total_expenses'])

    if not monthly_revenue.empty and not monthly_expenses.empty:
        pl_df = pd.merge(monthly_revenue, monthly_expenses,
                         left_on='sale_date__month', right_on='date__month', how='outer').fillna(0)
    elif not monthly_revenue.empty:
        pl_df = monthly_revenue.copy()
        pl_df['total_expenses'] = 0
        pl_df['date__month'] = pl_df['sale_date__month']
    elif not monthly_expenses.empty:
        pl_df = monthly_expenses.copy()
        pl_df['revenue'] = 0
        pl_df['collected'] = 0
        pl_df['sale_date__month'] = pl_df['date__month']
    else:
        pl_df = pd.DataFrame()

    pl_table = []
    if not pl_df.empty:
        month_col = 'sale_date__month' if 'sale_date__month' in pl_df.columns else 'date__month'
        for _, row in pl_df.sort_values(month_col).iterrows():
            m_num = int(row.get(month_col, 0))
            revenue = float(row.get('revenue', 0) or 0)
            collected = float(row.get('collected', 0) or 0)
            expenses = float(row.get('total_expenses', 0) or 0)
            gross_profit = revenue - expenses
            pl_table.append({
                'month': months_map.get(m_num, '—'),
                'revenue': revenue, 'collected': collected,
                'outstanding': revenue - collected,
                'expenses': expenses, 'gross_profit': gross_profit,
                'margin': round((gross_profit / revenue * 100), 1) if revenue > 0 else 0,
            })

    total_revenue = sum(r['revenue'] for r in pl_table)
    total_collected = sum(r['collected'] for r in pl_table)
    total_expenses = sum(r['expenses'] for r in pl_table)
    total_profit = total_revenue - total_expenses
    total_outstanding = total_revenue - total_collected
    overall_margin = round((total_profit / total_revenue * 100), 1) if total_revenue > 0 else 0
    category_breakdown = expenses_qs.values('category').annotate(total=Sum('amount')).order_by('-total')

    if export == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="PL_Report_{year}.csv"'
        writer = csv.writer(response)
        writer.writerow(['ES & RI Enterprises — Profit & Loss', f'Year: {year}'])
        writer.writerow(['Month', 'Revenue', 'Collected', 'Outstanding', 'Expenses', 'Gross Profit', 'Margin %'])
        for row in pl_table:
            writer.writerow([row['month'], row['revenue'], row['collected'],
                             row['outstanding'], row['expenses'], row['gross_profit'], row['margin']])
        writer.writerow(['TOTALS', total_revenue, total_collected, total_outstanding,
                         total_expenses, total_profit, overall_margin])
        return response

    return render(request, 'core/profit_and_loss.html', {
        'year': year, 'month': month, 'pl_table': pl_table,
        'total_revenue': total_revenue, 'total_collected': total_collected,
        'total_expenses': total_expenses, 'total_profit': total_profit,
        'total_outstanding': total_outstanding, 'overall_margin': overall_margin,
        'category_breakdown': category_breakdown, 'branch': branch,
        'title': f'Profit & Loss — {year}',
        'years': range(2024, timezone.now().year + 1),
        'months_map': months_map, 'selected_month': month,
    })


# ─── API ─────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard_summary(request):
    today = timezone.now().date()
    branch = get_branch_filter(request.user)

    sales_qs = Sale.objects.all()
    expenses_qs = Expense.objects.all()
    customers_qs = Customer.objects.all()
    products_qs = Product.objects.all()

    if branch:
        sales_qs = sales_qs.filter(branch=branch)
        expenses_qs = expenses_qs.filter(branch=branch)
        customers_qs = customers_qs.filter(branch=branch)
        products_qs = products_qs.filter(branch=branch)

    today_sales = sales_qs.filter(sale_date=today).aggregate(total=Sum('total_amount'))['total'] or 0
    today_expenses = expenses_qs.filter(date=today).aggregate(total=Sum('amount'))['total'] or 0
    monthly_sales = sales_qs.filter(sale_date__year=today.year, sale_date__month=today.month).aggregate(
        total=Sum('total_amount'))['total'] or 0
    monthly_expenses = expenses_qs.filter(date__year=today.year, date__month=today.month).aggregate(
        total=Sum('amount'))['total'] or 0

    return Response({
        'date': today,
        'branch': branch.name if branch else 'All Branches',
        'today': {
            'sales_tzs': float(today_sales),
            'expenses_tzs': float(today_expenses),
            'net_tzs': float(today_sales - today_expenses),
        },
        'this_month': {
            'sales_tzs': float(monthly_sales),
            'expenses_tzs': float(monthly_expenses),
            'gross_profit_tzs': float(monthly_sales - monthly_expenses),
        },
        'alerts': {
            'overdue_customers': customers_qs.filter(balance_owed__gt=0).count(),
            'overdue_amount_tzs': float(
                customers_qs.filter(balance_owed__gt=0).aggregate(
                    total=Sum('balance_owed'))['total'] or 0),
            'low_stock_products': products_qs.filter(
                current_stock__lte=F('min_threshold'), is_active=True).count(),
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_stock_status(request):
    branch = get_branch_filter(request.user)
    products = Product.objects.filter(is_active=True)
    if branch:
        products = products.filter(branch=branch)

    stock_data = [{
        'id': p.id, 'name': p.name, 'branch': p.branch.name,
        'category': p.category, 'unit': p.unit,
        'current_stock': float(p.current_stock),
        'min_threshold': float(p.min_threshold),
        'is_low': p.current_stock <= p.min_threshold,
        'selling_price_tzs': float(p.selling_price) if p.selling_price else None,
    } for p in products]

    return Response({
        'branch': branch.name if branch else 'All Branches',
        'total_products': len(stock_data),
        'low_stock_count': sum(1 for p in stock_data if p['is_low']),
        'products': stock_data,
    })

@role_required('admin', 'owner')
def user_list(request):
    users = User.objects.all().order_by('role', 'username')
    return render(request, 'core/user_list.html', {
        'title': 'User Management',
        'users': users,
    })


@role_required('admin', 'owner')
def user_create(request):
    branches = Branch.objects.filter(status='active')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        role = request.POST.get('role', '').strip()
        branch_id = request.POST.get('branch', '').strip()
        phone = request.POST.get('phone_number', '').strip()
        password = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()

        errors = []
        if not username:
            errors.append('Username is required.')
        if not role:
            errors.append('Role is required.')
        if not password:
            errors.append('Password is required.')
        if password != password2:
            errors.append('Passwords do not match.')
        if User.objects.filter(username=username).exists():
            errors.append(f'Username "{username}" is already taken.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            try:
                branch = Branch.objects.get(id=branch_id) if branch_id else None
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    role=role,
                    branch=branch,
                    phone_number=phone,
                )
                messages.success(request, f'Account created for {username} ({role}).')
                return redirect('user_list')
            except Exception as e:
                messages.error(request, str(e))

    return render(request, 'core/user_create.html', {
        'title': 'Create User Account',
        'branches': branches,
        'roles': ['owner', 'branch_manager', 'clerk', 'viewer'],
    })


@role_required('admin', 'owner')
def user_edit(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    branches = Branch.objects.filter(status='active')

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update':
            target_user.first_name = request.POST.get('first_name', '').strip()
            target_user.last_name = request.POST.get('last_name', '').strip()
            target_user.email = request.POST.get('email', '').strip()
            target_user.role = request.POST.get('role', target_user.role)
            target_user.phone_number = request.POST.get('phone_number', '').strip()
            branch_id = request.POST.get('branch', '')
            target_user.branch = Branch.objects.get(id=branch_id) if branch_id else None
            target_user.save()
            messages.success(request, f'{target_user.username} updated successfully.')
            return redirect('user_list')

        elif action == 'reset_password':
            new_password = request.POST.get('new_password', '').strip()
            confirm_password = request.POST.get('confirm_password', '').strip()
            if not new_password:
                messages.error(request, 'New password cannot be empty.')
            elif new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
            else:
                target_user.set_password(new_password)
                target_user.save()
                messages.success(request, f'Password reset for {target_user.username}.')
                return redirect('user_list')

        elif action == 'toggle_active':
            target_user.is_active = not target_user.is_active
            target_user.save()
            status = 'activated' if target_user.is_active else 'deactivated'
            messages.success(request, f'{target_user.username} {status}.')
            return redirect('user_list')

    return render(request, 'core/user_edit.html', {
        'title': f'Edit User — {target_user.username}',
        'target_user': target_user,
        'branches': branches,
        'roles': ['owner', 'branch_manager', 'clerk', 'viewer'],
    })

@login_required
@role_required('admin', 'owner', 'branch_manager')
def cash_flow_report(request):
    from django.db.models import Sum, Q
    import json

    branch = request.GET.get('branch')
    month = request.GET.get('month', str(datetime.today().month))
    year = request.GET.get('year', str(datetime.today().year))

    try:
        month = int(month)
        year = int(year)
    except ValueError:
        month = datetime.today().month
        year = datetime.today().year

    # Base filters
    sale_filter = Q(sale_date__month=month, sale_date__year=year)
    expense_filter = Q(date__month=month, date__year=year)
    purchase_filter = Q(purchase_date__month=month, purchase_date__year=year)

    if request.user.role == 'branch_manager' and request.user.branch:
        sale_filter &= Q(branch=request.user.branch)
        expense_filter &= Q(branch=request.user.branch)
        purchase_filter &= Q(branch=request.user.branch)
    elif branch:
        sale_filter &= Q(branch_id=branch)
        expense_filter &= Q(branch_id=branch)
        purchase_filter &= Q(branch_id=branch)

    # Sales breakdown
    sales = Sale.objects.filter(sale_filter)
    total_sales = sales.aggregate(t=Sum('total_amount'))['t'] or 0
    cash_sales = sales.filter(payment_method='cash').aggregate(t=Sum('total_amount'))['t'] or 0
    credit_sales = sales.filter(payment_method='credit').aggregate(t=Sum('total_amount'))['t'] or 0
    partial_sales = sales.filter(payment_method='partial').aggregate(t=Sum('total_amount'))['t'] or 0
    cash_received_partial = sales.filter(payment_method='partial').aggregate(t=Sum('amount_paid'))['t'] or 0

    # Actual cash received = cash sales + partial payments received
    actual_cash_in = cash_sales + cash_received_partial

    # Uncollected credit
    uncollected = credit_sales + (partial_sales - cash_received_partial)

    # Expenses (cash out)
    total_expenses = Expense.objects.filter(expense_filter).aggregate(t=Sum('amount'))['t'] or 0

    # Stock purchases (cash locked in stock)
    stock_purchases = StockPurchase.objects.filter(purchase_filter).aggregate(
        t=Sum(F('quantity') * F('cost_per_unit'))
    )['t'] or 0

    # Net cash position
    net_cash = actual_cash_in - total_expenses - stock_purchases

    # Monthly trend (last 6 months)
    trend = []
    for i in range(5, -1, -1):
        d = datetime(year, month, 1) - timedelta(days=i * 30)
        m, y = d.month, d.year
        s = Sale.objects.filter(sale_date__month=m, sale_date__year=y)
        if request.user.role == 'branch_manager' and request.user.branch:
            s = s.filter(branch=request.user.branch)
        cash_in = s.filter(payment_method='cash').aggregate(t=Sum('total_amount'))['t'] or 0
        cash_in += s.filter(payment_method='partial').aggregate(t=Sum('amount_paid'))['t'] or 0
        exp = Expense.objects.filter(date__month=m, date__year=y)
        if request.user.role == 'branch_manager' and request.user.branch:
            exp = exp.filter(branch=request.user.branch)
        cash_out = exp.aggregate(t=Sum('amount'))['t'] or 0
        trend.append({
            'month': d.strftime('%b %Y'),
            'cash_in': float(cash_in),
            'cash_out': float(cash_out),
            'net': float(cash_in - cash_out),
        })

    branches = Branch.objects.filter(status='active')
    months = [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)]
    years = list(range(2024, datetime.today().year + 1))

    return render(request, 'core/cash_flow_report.html', {
        'title': 'Cash Flow Report',
        'total_sales': total_sales,
        'actual_cash_in': actual_cash_in,
        'uncollected': uncollected,
        'total_expenses': total_expenses,
        'stock_purchases': stock_purchases,
        'net_cash': net_cash,
        'trend_json': json.dumps(trend),
        'trend': trend,
        'branches': branches,
        'months': months,
        'years': years,
        'selected_month': month,
        'selected_year': year,
        'selected_branch': branch,
    })