# core/forms.py
from django import forms
from django.db.models import Q
from .models import Expense, Branch, Production, Product, Customer, Sale, SaleItem, TripLog, BankDeposit
from .models import Supplier, Truck, SpendingRequest, EXPENSE_CATEGORIES
from django.forms import formset_factory
from django.contrib.auth.password_validation import validate_password
from .models import User, Branch
from django.utils.translation import gettext_lazy as _

class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'product': _('Product'),
            'quantity': _('Quantity'),
            'unit_price': _('Unit Price (TZS)'),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role in ['admin', 'owner']:
            self.fields['product'].queryset = Product.objects.filter(
                is_raw_material=False
            ).filter(Q(current_stock__gt=0) | Q(track_stock=False))
        elif user and user.branch:
            self.fields['product'].queryset = Product.objects.filter(
                branch=user.branch,
                is_raw_material=False
            ).filter(Q(current_stock__gt=0) | Q(track_stock=False))


SaleItemFormSet = formset_factory(SaleItemForm, extra=1, can_delete=True)


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['branch','customer', 'truck', 'payment_method', 'amount_paid']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'branch': _('Branch'),
            'customer': _('Customer'),
            'truck': _('Truck'),
            'payment_method': _('Payment Method'),
            'amount_paid': _('Amount Paid (TZS)'),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role not in ['admin', 'owner'] and user.branch:
            self.fields['customer'].queryset = Customer.objects.filter(branch=user.branch)
            self.fields['branch'].widget = forms.HiddenInput()
            self.fields['branch'].required = False
            self.fields['branch'].initial = user.branch

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['branch', 'truck', 'category', 'amount', 'description', 'receipt_image', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'branch': _('Branch'),
            'truck': _('Truck'),
            'category': _('Category'),
            'amount': _('Amount (TZS)'),
            'description': _('Description'),
            'receipt_image': _('Receipt Image'),
            'date': _('Date'),
        }


class ProductionForm(forms.ModelForm):
    class Meta:
        model = Production
        fields = ['product', 'quantity', 'labor_cost', 'notes', 'production_date']
        widgets = {
            'production_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)  # pass user from view
        super().__init__(*args, **kwargs)
        if user and user.role not in ['admin', 'owner'] and user.branch:
            self.fields['product'].queryset = Product.objects.filter(
                branch=user.branch,
                is_raw_material=False  # only finished goods
            )

class TripLogForm(forms.ModelForm):
    class Meta:
        model = TripLog
        fields = ['truck', 'sale', 'start_odometer', 'end_odometer', 'fuel_used', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'truck': forms.Select(attrs={'class': 'form-select'}),
            'sale': forms.Select(attrs={'class': 'form-select'}),
            'start_odometer': forms.NumberInput(attrs={'class': 'form-control'}),
            'end_odometer': forms.NumberInput(attrs={'class': 'form-control'}),
            'fuel_used': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_odometer')
        end = cleaned_data.get('end_odometer')
        if end is not None and start is not None and end < start:
            raise forms.ValidationError("End odometer cannot be less than start odometer.")
        return cleaned_data

PAY_METHODS = [('cash', 'Cash'), ('mobile_money', 'Mobile Money'), ('bank_transfer', 'Bank Transfer')]


class BootstrapMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            css = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs.setdefault('class', css)


class StockPurchaseForm(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Product'
    )
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Quantity Received'
    )
    cost_per_unit = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Cost per Unit (TZS) — optional'
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True), required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Supplier from list — choose one to record a bill'
    )
    supplier_name = forms.CharField(
        max_length=200, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Or type a supplier name — optional'
    )
    amount_paid_now = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Paid now (TZS) — only with a listed supplier; leave empty if taken on credit'
    )
    payment_method = forms.ChoiceField(
        choices=PAY_METHODS, required=False, initial='cash',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='How the amount paid now was paid'
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Pay supplier by — optional'
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Date'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Notes — optional'
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            if user.role in ['admin', 'owner']:
                self.fields['product'].queryset = Product.objects.all()
            elif user.branch:
                self.fields['product'].queryset = Product.objects.filter(branch=user.branch)


class SupplierForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ['name', 'phone', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 2})}


class SupplierBillForm(BootstrapMixin, forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(is_active=True))
    branch = forms.ModelChoiceField(queryset=Branch.objects.all(), required=False,
                                    label='Branch (owner/admin only)')
    category = forms.ChoiceField(choices=EXPENSE_CATEGORIES)
    description = forms.CharField(max_length=255, label='What was bought')
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=1, label='Total amount (TZS)')
    bill_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Date')
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}),
                               label='Pay supplier by — optional')
    reference = forms.CharField(max_length=100, required=False, label='Invoice / delivery note no. — optional')
    amount_paid_now = forms.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0,
                                         label='Paid now (TZS) — leave empty if all on credit')
    payment_method = forms.ChoiceField(choices=PAY_METHODS, required=False, initial='cash',
                                       label='How the amount paid now was paid')
    truck = forms.ModelChoiceField(queryset=Truck.objects.all(), required=False,
                                   label='Truck (if this is a truck cost)')


class BillPayForm(BootstrapMixin, forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=1, label='Amount paid (TZS)')
    method = forms.ChoiceField(choices=PAY_METHODS, label='Paid by')
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}), label='Date paid')
    notes = forms.CharField(max_length=255, required=False, label='Note — optional')


class SpendingRequestForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SpendingRequest
        fields = ['amount', 'reason']
        widgets = {'reason': forms.Textarea(attrs={'rows': 3})}
        labels = {'amount': 'Amount needed (TZS)', 'reason': 'What it is for and why'}
        
class StockPurchaseFormOld(forms.Form):
    product = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Product'
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Quantity Received'
    )
    cost_per_unit = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label='Cost per Unit (TZS) — optional'
    )
    supplier_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Supplier Name — optional'
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        label='Date'
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Notes — optional'
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            if user.role in ['admin', 'owner']:
                self.fields['product'].queryset = Product.objects.all()
            elif user.branch:
                self.fields['product'].queryset = Product.objects.filter(branch=user.branch)

class UserCreateForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Username'
    )
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='First Name'
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Last Name'
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        label='Email'
    )
    role = forms.ChoiceField(
        choices=[
            ('owner', 'Business Owner'),
            ('branch_manager', 'Branch Manager'),
            ('clerk', 'Sales Clerk'),
            ('viewer', 'Read Only'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Role'
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.filter(status='active'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Branch'
    )
    phone_number = forms.CharField(
        max_length=15,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='Phone Number'
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password'
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Confirm Password'
    )

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError(f'Username "{username}" is already taken.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password2 = cleaned_data.get('password2')
        if password and password2 and password != password2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'role', 'branch', 'phone_number', 'is_active']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(status='active')
        self.fields['branch'].required = False

class BankDepositForm(forms.ModelForm):
    class Meta:
        model = BankDeposit
        fields = ['branch', 'amount', 'deposit_date', 'reference', 'notes']
        widgets = {
            'deposit_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
        labels = {
            'branch': _('Branch'),
            'amount': _('Amount Deposited (TZS)'),
            'deposit_date': _('Deposit Date'),
            'reference': _('Deposit Slip / Reference No.'),
            'notes': _('Notes'),
        }