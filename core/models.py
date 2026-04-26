from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal

from core.middleware import get_current_branch

class Branch(models.Model):
    name = models.CharField(max_length=100)          # e.g. "Same", "Ishinde"
    location = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active'
    )
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Product(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)          # e.g. "Cement 32.5 50kg", "6-inch Block"
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    category = models.CharField(
        max_length=50,
        choices=[
            ('raw_material', 'Raw Material'),
            ('blocks', 'Concrete Blocks'),
            ('timber', 'Timber Products'),
            ('pebbles', 'Pebbles/Aggregates'),
            ('hardware', 'Hardware'),
        ]
    )
    unit = models.CharField(max_length=20)           # bag, piece, cubic_meter, etc.
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    min_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_raw_material = models.BooleanField(default=False)   # key flag for production
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} ({self.branch.name})"

    def get_production_recipe(self):
        """
        Returns dict of {raw_product_id: quantity_per_unit} for this finished product.
        Supports Cement 32.5 and 42.5 with different block production rates.
        """
        name_lower = self.name.lower()

        if 'block' not in name_lower:
            return {}  # No recipe for non-block products

        # Find available cements in the same branch
        cement_325 = Product.objects.filter(
            branch=self.branch,
            name__icontains='32.5',
            is_raw_material=True
        ).first()

        cement_425 = Product.objects.filter(
            branch=self.branch,
            name__icontains='42.5',
            is_raw_material=True
        ).first()

        sand = Product.objects.filter(
            branch=self.branch,
            name__icontains='sand',
            is_raw_material=True
        ).first()

        if not sand:
            raise ValueError("Sand not found in this branch")

        recipe = {}

        # Determine block size
        is_6inch = '6' in name_lower or '6-inch' in name_lower
        is_5inch = '5' in name_lower or '5-inch' in name_lower

        if is_6inch:
            if cement_425:
                # 42.5 cement → 38 blocks per bag (your latest rule)
                recipe[cement_425.id] = Decimal('1') / Decimal('38')  # 0.025 bags per block
            else:
                raise ValueError("6-inch blocks require Cement 42.5 (not found in this branch)")

        elif is_5inch:
            if cement_325:
                # 32.5 cement → 35 blocks per bag
                recipe[cement_325.id] = Decimal('1') / Decimal('35')  # ≈ 0.02857 bags per block
            elif cement_425:
                # 42.5 cement → 40 blocks per bag (also allowed for 5-inch)
                recipe[cement_425.id] = Decimal('1') / Decimal('40')  # ≈ 0.02632 bags per block
            else:
                raise ValueError("5-inch blocks require Cement 32.5 or 42.5 (not found in this branch)")

        else:
            raise ValueError(f"No production recipe defined for product: {self.name}")

        # Sand consumption (depends on which cement is used)
        if recipe:
            cement_id = list(recipe.keys())[0]
            cement = Product.objects.get(id=cement_id)

            if '32.5' in cement.name:
                # 100 bags of 32.5 cement use 40 m³ sand → 0.4 m³ per block
                sand_per_block = Decimal('40') / Decimal('100')
            else:  # 42.5
                # 100 bags of 42.5 cement use 32 m³ sand → 0.32 m³ per block
                sand_per_block = Decimal('32') / Decimal('100')

            recipe[sand.id] = sand_per_block

        return recipe

    class Meta:
        ordering = ['branch', 'name']
        indexes = [
            models.Index(fields=['branch', 'is_active']),
            models.Index(fields=['current_stock']),
        ]


class Truck(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, related_name='trucks')
    plate_number = models.CharField(max_length=20, unique=True)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_odometer = models.IntegerField(default=0, help_text="Last recorded km")
    last_maintenance_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('maintenance', 'Maintenance'), ('sold', 'Sold')],
        default='active'
    )
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.plate_number

class TripLog(models.Model):
    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='trips')
    sale = models.ForeignKey('Sale', on_delete=models.SET_NULL, null=True, blank=True)
    start_odometer = models.IntegerField()
    end_odometer = models.IntegerField(null=True, blank=True)
    fuel_used = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Liters")
    distance_km = models.IntegerField(null=True, blank=True)
    date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.end_odometer:
            self.distance_km = self.end_odometer - self.start_odometer
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Trip {self.truck} - {self.date}"

EXPENSE_CATEGORIES = [
    ('raw_materials', 'Raw Materials & Inputs (cement, sand, aggregates, timber)'),
    ('production_labor', 'Production Labor & Wages'),
    ('truck_operations', 'Truck Operations (fuel, diesel, petrol, delivery)'),
    ('truck_maintenance', 'Truck Repairs & Maintenance'),
    ('administration', 'Administration (rent, electricity, office supplies, admin salaries)'),
    ('depreciation', 'Depreciation (equipment, machinery, trucks)'),
    ('other_allowable', 'Other Allowable Deductions'),
]

class Expense(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='expenses')
    truck = models.ForeignKey(Truck, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(
    max_length=50,
    choices=EXPENSE_CATEGORIES,
    default='other_allowable'
)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    receipt_image = models.ImageField(upload_to='receipts/%Y/%m/%d/', null=True, blank=True)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.category} - {self.amount} TZS"


class Production(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='productions')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='productions')  # finished good
    quantity = models.DecimalField(max_digits=12, decimal_places=2)  # number of blocks produced
    raw_materials_consumed = models.JSONField(default=dict)          # e.g. {"cement_id": 10.5, "sand_id": 2.3}
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    production_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.quantity} × {self.product.name} on {self.production_date}"
    
class Customer(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_owed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']

class Sale(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('credit', 'Credit'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='sales')
    truck = models.ForeignKey(Truck, on_delete=models.SET_NULL, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=20, choices=[
        ('paid', 'Paid'),
        ('partial', 'Partial'),
        ('credit', 'Credit'),
    ], default='paid')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True)
    sale_date = models.DateField(default=timezone.now)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Sale #{self.id} - {self.sale_date}"

    def save(self, *args, **kwargs):
        if self.amount_paid >= self.total_amount:
            self.payment_status = 'paid'
        elif self.amount_paid > 0:
            self.payment_status = 'partial'
        else:
            self.payment_status = 'credit'
        super().save(*args, **kwargs)


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

# Custom User with roles
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'System Administrator'),
        ('owner', 'Business Owner'),
        ('branch_manager', 'Branch Manager'),
        ('clerk', 'Sales Clerk'),
        ('viewer', 'Read Only'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='clerk')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.username

    def can_access_branch(self, branch):
        if self.role in ['admin', 'owner']:
            return True
        return self.branch == branch
    

from django.db.models import Manager


class BranchFilteredManager(Manager):
    def get_queryset(self, *args, **kwargs):
        qs = super().get_queryset(*args, **kwargs)
        branch_id = get_current_branch()
        if branch_id is not None:
            # Filter by current branch
            qs = qs.filter(branch_id=branch_id)
        return qs

class InventoryLog(models.Model):
    MOVEMENT_TYPES = [
        ('purchase', 'Stock Purchase'),
        ('sale', 'Sale'),
        ('production_in', 'Production Output'),
        ('production_out', 'Raw Material Used'),
        ('adjustment', 'Manual Adjustment'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_logs')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='inventory_logs')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)  # positive = in, negative = out
    stock_before = models.DecimalField(max_digits=12, decimal_places=2)
    stock_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference_note = models.CharField(max_length=200, blank=True)  # e.g. "Sale #12", "Production #5"
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.movement_type} | {self.product.name} | {self.quantity}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['branch', 'created_at']),
        ]

# Apply to relevant models
Product.add_to_class('objects', BranchFilteredManager())
Expense.add_to_class('objects', BranchFilteredManager())
Production.add_to_class('objects', BranchFilteredManager())
Truck.add_to_class('objects', BranchFilteredManager())
Sale.add_to_class('objects', BranchFilteredManager())
Customer.add_to_class('objects', BranchFilteredManager())
InventoryLog.add_to_class('objects', BranchFilteredManager())