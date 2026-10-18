from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    Branch, Product, Truck, Expense, Production, User, Customer, Sale, SaleItem, TripLog, InventoryLog
)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'status', 'created_at')
    search_fields = ('name', 'location')



@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'category', 'is_raw_material', 'current_stock', 'min_threshold')
    list_filter = ('branch', 'category', 'is_raw_material')
    search_fields = ('name', 'sku')


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'branch', 'status', 'purchase_date')
    list_filter = ('branch', 'status')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('category', 'amount', 'branch', 'truck', 'date', 'description_short')
    list_filter = ('category', 'branch', 'date')
    search_fields = ('description',)
    date_hierarchy = 'date'

    def description_short(self, obj):
        return obj.description[:50] + '...' if obj.description else ''
    description_short.short_description = 'Description'


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'branch', 'production_date', 'labor_cost')
    list_filter = ('branch', 'production_date')
    date_hierarchy = 'production_date'


# ────────────────────────────────────────────────
#  FIXED: Custom User admin with password handling
# ────────────────────────────────────────────────
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'branch', 'is_staff', 'is_active')
    list_filter = ('role', 'branch', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('username',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
        ('Custom Fields', {'fields': ('role', 'branch')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role', 'branch', 'is_staff', 'is_active'),
        }),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch', 'phone', 'credit_limit', 'balance_owed', 'is_active')
    list_filter = ('branch', 'is_active')
    search_fields = ('name', 'phone')


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale_date', 'branch', 'customer', 'total_amount', 'payment_status', 'amount_paid')
    list_filter = ('branch', 'payment_status', 'sale_date')
    date_hierarchy = 'sale_date'


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')


@admin.register(TripLog)
class TripLogAdmin(admin.ModelAdmin):
    list_display = ('truck', 'date', 'distance_km', 'fuel_used')
    list_filter = ('truck', 'date')

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ('product', 'branch', 'movement_type', 'quantity', 'stock_before', 'stock_after', 'created_at')
    list_filter = ('branch', 'movement_type', 'created_at')
    search_fields = ('product__name', 'reference_note')
    date_hierarchy = 'created_at'
    readonly_fields = ('stock_before', 'stock_after', 'created_at')