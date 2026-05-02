# core/forms.py
from django import forms
from .models import Expense, Branch, Production, Product, Customer, Sale, SaleItem, TripLog
from django.forms import formset_factory
from django.contrib.auth.password_validation import validate_password
from .models import User, Branch

class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role not in ['admin', 'owner'] and user.branch:
            self.fields['product'].queryset = Product.objects.filter(
                branch=user.branch,
                is_raw_material=False,
                current_stock__gt=0  # only sell available stock
            )


SaleItemFormSet = formset_factory(SaleItemForm, extra=1, can_delete=True)


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ['branch','customer', 'truck', 'payment_method', 'amount_paid']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user and user.role not in ['admin', 'owner'] and user.branch:
            self.fields['customer'].queryset = Customer.objects.filter(branch=user.branch)

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['branch', 'truck', 'category', 'amount', 'description', 'receipt_image', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'category': forms.Select(attrs={'class': 'form-select'}),
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

class StockPurchaseForm(forms.Form):
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