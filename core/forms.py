# core/forms.py
from django import forms
from .models import Expense, Branch, Production, Product, Customer, Sale, SaleItem, TripLog
from django.forms import formset_factory

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