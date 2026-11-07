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
            ('electrical', 'Electrical'),
            ('plumbing', 'Plumbing'),
            ('paint', 'Paint & Finishing'),
            ('tools', 'Tools'),
            ('services', 'Services'),
        ]
    )
    unit = models.CharField(max_length=20)           # bag, piece, cubic_meter, etc.
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    min_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_raw_material = models.BooleanField(default=False)   # key flag for production
    track_stock = models.BooleanField(
        default=True,
        help_text="Untick for services or goods delivered straight to the customer (transport, direct sand delivery). Stock is then not checked or reduced."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.name} ({self.branch.name})"


    # ── Block recipes, one per branch: edit these numbers if the mix changes ──
    BLOCK_RECIPES = {
        # 8 bags of 42.5 + 4 m3 sand -> 352 blocks
        'same': {'cement': '42.5', 'blocks_per_bag': Decimal('44'),
                 'sand_m3_per_bag': Decimal('0.5')},
        # 6 bags of 32.5 + 2.2 m3 sand (full truck) -> 210 blocks
        'ishinde': {'cement': '32.5', 'blocks_per_bag': Decimal('35'),
                    'sand_m3_per_bag': Decimal('2.2') / Decimal('6')},
    }
    # Size of ONE unit of your sand product, in m3 (1 if sand is counted in m3)
    SAND_UNIT_M3 = Decimal('1')

    def _find_sand(self):
        return Product.objects.filter(
            branch=self.branch, is_raw_material=True
        ).filter(
            models.Q(name__icontains='sand') | models.Q(name__icontains='mchanga')
        ).first()

    def get_sand_product_id(self):
        sand = self._find_sand()
        return sand.id if sand else None

    def get_production_recipe(self):
        """Returns {raw_product_id: quantity needed per finished block}."""
        name_lower = self.name.lower()
        if 'block' not in name_lower and 'tofali' not in name_lower:
            return {}

        spec = self.BLOCK_RECIPES.get(self.branch.name.strip().lower())
        if not spec:
            raise ValueError(f"No block recipe is set for the {self.branch.name} branch")

        cement = Product.objects.filter(
            branch=self.branch, name__icontains=spec['cement'], is_raw_material=True
        ).first()
        if not cement:
            raise ValueError(f"Cement {spec['cement']} not found in the {self.branch.name} branch")

        sand = self._find_sand()
        if not sand:
            raise ValueError("Sand not found in this branch")

        blocks_per_bag = spec['blocks_per_bag']
        return {
            cement.id: Decimal('1') / blocks_per_bag,
            sand.id: (spec['sand_m3_per_bag'] / blocks_per_bag) / self.SAND_UNIT_M3,
        }

    def get_production_recipe_old(self):
        """
        Returns dict of {raw_product_id: quantity_per_unit} for this finished product.
        Supports Cement 32.5 and 42.5 with different block production rates.
        """
        name_lower = self.name.lower()

        if 'block' not in name_lower and 'tofali' not in name_lower:
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
             is_raw_material=True
        ).filter(
            models.Q(name__icontains='sand') | models.Q(name__icontains='mchanga')
        ).first()

        if not sand:
            raise ValueError("Sand not found in this branch")

        recipe = {}

        # Determine block size
        is_6inch = '6' in name_lower or '6-inch' in name_lower
        is_5inch = '5' in name_lower or '5-inch' in name_lower

        if is_6inch:
            if cement_425:
                # 1 bag cement 42.5 → 36 blocks (6 inch)
                recipe[cement_425.id] = Decimal('1') / Decimal('36')
            else:
                raise ValueError("6-inch blocks require Cement 42.5 (not found in this branch)")

        elif is_5inch:
            if cement_325:
                # 1 bag cement 32.5 → 40 blocks (5 inch)
                recipe[cement_325.id] = Decimal('1') / Decimal('40')
            elif cement_425:
                # 1 bag cement 42.5 → 40 blocks (5 inch)
                recipe[cement_425.id] = Decimal('1') / Decimal('40')
            else:
                raise ValueError("5-inch blocks require Cement 32.5 or 42.5 (not found in this branch)")

        else:
            raise ValueError(f"No production recipe defined for product: {self.name}")

        # Sand consumption (depends on which cement is used)
        # Sand consumption based on real business data:
        # 1 truck trip mchanga = 8 bags cement for both block sizes
        # 6 inch: 1 bag = 36 blocks → 1 trip covers 288 blocks
        # 5 inch: 1 bag = 40 blocks → 1 trip covers 320 blocks
        if recipe:
            if is_6inch:
                sand_per_block = Decimal('1') / Decimal('288')
            else:  # 5 inch
                sand_per_block = Decimal('1') / Decimal('320')

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

    PAYMENT_SOURCES = [
        ('cash', 'Cash'),
        ('bank_mobile', 'Bank / Mobile Money'),
        ('credit', 'On Supplier Credit'),
    ]
    payment_source = models.CharField(max_length=20, choices=PAYMENT_SOURCES, default='cash')
    is_stock_purchase = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.category} - {self.amount} TZS"


class BankDeposit(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='bank_deposits')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    deposit_date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, help_text="Deposit slip number or bank reference")
    notes = models.TextField(blank=True)
    logged_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Deposit {self.amount} TZS - {self.branch} - {self.deposit_date}"

    class Meta:
        ordering = ['-deposit_date']


class Production(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='productions')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='productions')  # finished good
    quantity = models.DecimalField(max_digits=12, decimal_places=2)  # number of blocks produced
    raw_materials_consumed = models.JSONField(default=dict)          # e.g. {"cement_id": 10.5, "sand_id": 2.3}
    labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_note = models.CharField(max_length=255, blank=True)
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
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if self._state.adding and not self.unit_cost:
            self.unit_cost = self.product.cost_price or 0
        super().save(*args, **kwargs)

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

class Payment(models.Model):
    METHODS = [
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    KINDS = [
        ('sale', 'Paid at time of sale'),
        ('repayment', 'Customer repayment'),
    ]
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHODS, default='cash')
    kind = models.CharField(max_length=20, choices=KINDS, default='sale')
    payment_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.amount} TZS ({self.method}) on {self.payment_date}"

    class Meta:
        ordering = ['-payment_date', '-id']


class AuditLog(models.Model):
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50)
    object_repr = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

class Supplier(models.Model):
    name = models.CharField(max_length=200, unique=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class SupplierBill(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='bills')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='supplier_bills')
    bill_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    description = models.CharField(max_length=255)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expense = models.ForeignKey(Expense, on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_bills')
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def balance(self):
        return self.total_amount - self.amount_paid

    @property
    def is_overdue(self):
        return bool(self.due_date and self.balance > 0 and self.due_date < timezone.now().date())

    def __str__(self):
        return f"{self.supplier.name} - {self.total_amount} TZS ({self.bill_date})"


class SupplierPayment(models.Model):
    METHODS = [
        ('cash', 'Cash'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    bill = models.ForeignKey(SupplierBill, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHODS, default='cash')
    payment_date = models.DateField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)
    paid_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.amount} TZS to {self.bill.supplier.name}"

    class Meta:
        ordering = ['-payment_date', '-id']


class SpendingRequest(models.Model):
    STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('used', 'Used'),
    ]
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)
    requested_by = models.ForeignKey('User', on_delete=models.CASCADE, related_name='spending_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    decided_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_requests')
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Request #{self.id}: {self.amount} TZS ({self.status})"

class Target(models.Model):
    METRICS = [
        ('sales', 'Sales (TZS)'),
        ('gross_profit', 'Gross profit (TZS)'),
        ('running_costs', 'Running costs limit (TZS)'),
        ('production', 'Blocks produced'),
    ]
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='targets')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    metric = models.CharField(max_length=20, choices=METRICS)
    value = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        unique_together = ('branch', 'year', 'month', 'metric')
        ordering = ['-year', '-month', 'branch']

    def __str__(self):
        return f"{self.branch.name} {self.year}-{self.month:02d} {self.metric}: {self.value}"

class OpeningCash(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='opening_cash')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    counted_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ('branch', 'year', 'month')
        ordering = ['-year', '-month', 'branch']

    def __str__(self):
        return f"{self.branch.name} {self.year}-{self.month:02d}: {self.amount}"