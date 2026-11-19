from datetime import timedelta
from django.core.management.base import BaseCommand
from core.models import Expense, Production


def line(e):
    return (f"  id {e.id} | {e.date} | {e.branch.name} | {e.get_category_display()[:28]} | "
            f"{e.amount:,.0f} | {e.payment_source} | {(e.description or '')[:60]}")


def near(day):
    return (day - timedelta(days=1), day + timedelta(days=1))


class Command(BaseCommand):
    help = 'List expenses that may repeat production labour or stock purchases. Use --mark IDs to keep them out of running costs.'

    def add_arguments(self, parser):
        parser.add_argument('--mark', type=str, default='',
                            help='Comma-separated expense ids to mark as already counted in product cost')

    def handle(self, *args, **options):
        if options['mark']:
            ids = [int(x) for x in options['mark'].split(',') if x.strip().isdigit()]
            count = 0
            for e in Expense.objects.filter(id__in=ids):
                e.in_product_cost = True
                e.save(update_fields=['in_product_cost'])
                count += 1
            self.stdout.write(self.style.SUCCESS(
                f'Marked {count} expenses as already counted in product cost.'))
            return

        base = Expense.objects.filter(
            is_stock_purchase=False, in_product_cost=False).select_related('branch')

        self.stdout.write('\nA) Same amount as production labour (same branch, within 1 day):')
        seen = set()
        for prod in Production.objects.filter(labor_cost__gt=0).select_related('branch', 'product'):
            for e in base.filter(branch=prod.branch, amount=prod.labor_cost,
                                 date__range=near(prod.production_date)):
                if e.id not in seen:
                    seen.add(e.id)
                    self.stdout.write(line(e) + f'   <- production #{prod.id}')

        self.stdout.write('\nB) "Production Labor & Wages" typed as an expense:')
        for e in base.filter(category='production_labor').order_by('date'):
            self.stdout.write(line(e))

        self.stdout.write('\nC) Same amount as a stock purchase (same branch, within 1 day):')
        seen = set()
        for p in Expense.objects.filter(is_stock_purchase=True).select_related('branch'):
            for e in base.filter(branch=p.branch, amount=p.amount, date__range=near(p.date)):
                if e.id not in seen:
                    seen.add(e.id)
                    self.stdout.write(line(e) + f'   <- stock purchase id {p.id}')

        self.stdout.write('\nD) All "Raw Materials & Inputs" typed by hand (review each):')
        for e in base.filter(category='raw_materials').order_by('date'):
            self.stdout.write(line(e))