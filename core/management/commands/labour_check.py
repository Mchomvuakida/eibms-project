from datetime import timedelta
from django.core.management.base import BaseCommand
from core.models import Production, Expense

KEYWORDS = ('wafyatu', 'mbanduaji', 'labour', 'vibarua')


class Command(BaseCommand):
    help = 'Show production runs with labour typed in, and labour expenses near each one'

    def handle(self, *args, **options):
        runs = Production.objects.filter(labor_cost__gt=0).select_related(
            'branch', 'product').order_by('production_date')
        if not runs:
            self.stdout.write('No production run has labour typed in.')
            return
        for p in runs:
            self.stdout.write(
                f"\nProduction #{p.id} | {p.production_date} | {p.branch.name} | "
                f"{p.product.name} | {p.quantity:,.0f} made | labour typed in: {p.labor_cost:,.0f}")
            nearby = Expense.objects.filter(
                category__in=['production_labor', 'cost_of_sales', 'raw_materials'],
                in_product_cost=False,
                date__range=(p.production_date - timedelta(days=3),
                             p.production_date + timedelta(days=3)),
            ).select_related('branch')
            for e in nearby:
                text = (e.description or '').lower()
                if any(k in text for k in KEYWORDS):
                    self.stdout.write(
                        f"    expense id {e.id} | {e.date} | {e.branch.name} | "
                        f"{e.amount:,.0f} | {(e.description or '')[:50]}")