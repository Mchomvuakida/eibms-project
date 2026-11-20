from django.core.management.base import BaseCommand
from core.models import Expense, InventoryLog

SKIP = ('washusha', 'washushaji', 'kushusha', 'dereva', 'posho')


class Command(BaseCommand):
    help = 'Compare cement added through Stock Purchase with cement typed by hand as expenses'

    def handle(self, *args, **options):
        self.stdout.write('Cement added through Stock Purchase:')
        logs = InventoryLog.objects.filter(
            movement_type='purchase', product__name__icontains='cement'
        ).select_related('product', 'branch').order_by('created_at')
        for l in logs:
            kind = 'raw material' if l.product.is_raw_material else 'for sale'
            self.stdout.write(
                f"  {l.created_at:%Y-%m-%d} | {l.branch.name} | {l.product.name} ({kind}) "
                f"| +{l.quantity:,.0f} | cost price now {l.product.cost_price or 0:,.0f}")

        self.stdout.write('\nStock Purchase expenses for cement (a cost was entered):')
        for e in Expense.objects.filter(
                is_stock_purchase=True, description__icontains='cement'
        ).select_related('branch').order_by('date'):
            self.stdout.write(f"  id {e.id} | {e.date} | {e.branch.name} | {e.amount:,.0f}")

        self.stdout.write('\nCement typed by hand as normal expenses:')
        for e in Expense.objects.filter(
                is_stock_purchase=False, description__icontains='cement'
        ).select_related('branch').order_by('date'):
            text = (e.description or '').lower()
            if any(w in text for w in SKIP):
                continue
            self.stdout.write(
                f"  id {e.id} | {e.date} | {e.branch.name} | {e.amount:,.0f} | {(e.description or '')[:50]}")