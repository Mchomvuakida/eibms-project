from django.core.management.base import BaseCommand
from django.db.models import Count, Sum, Q
from core.models import Product, SaleItem


class Command(BaseCommand):
    help = 'List products and sale lines that have no cost price'

    def handle(self, *args, **options):
        self.stdout.write('\nProducts in stock with no cost price:')
        products = Product.objects.filter(
            is_active=True, track_stock=True, current_stock__gt=0
        ).filter(Q(cost_price__isnull=True) | Q(cost_price=0)).select_related('branch')
        for p in products.order_by('branch__name', 'name'):
            self.stdout.write(
                f"  {p.branch.name} | {p.name} | stock {p.current_stock:,.0f} {p.unit} "
                f"| selling {p.selling_price or 0:,.0f}")

        self.stdout.write('\nSale lines with no cost, grouped by product:')
        rows = (SaleItem.objects.filter(unit_cost=0, product__track_stock=True)
                .values('product__name', 'product__branch__name', 'product__cost_price')
                .annotate(lines=Count('id'), revenue=Sum('total_price'))
                .order_by('-revenue'))
        for r in rows:
            flag = ('cost is set now -> run backfill_costs' if r['product__cost_price']
                    else 'STILL NO COST PRICE')
            self.stdout.write(
                f"  {r['product__branch__name']} | {r['product__name']} | {r['lines']} lines "
                f"| {r['revenue']:,.0f} TZS | {flag}")