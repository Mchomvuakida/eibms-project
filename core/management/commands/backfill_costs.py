from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Expense, SaleItem


class Command(BaseCommand):
    help = 'Mark past stock-purchase expenses and fill in cost on past sale lines'

    def handle(self, *args, **options):
        with transaction.atomic():
            marked = Expense.objects.filter(
                category='raw_materials',
                is_stock_purchase=False,
                description__startswith='Purchase:',
            ).update(is_stock_purchase=True)

            to_update = []
            for item in SaleItem.objects.filter(unit_cost=0).select_related('product'):
                if item.product.cost_price:
                    item.unit_cost = item.product.cost_price
                    to_update.append(item)
            SaleItem.objects.bulk_update(to_update, ['unit_cost'], batch_size=200)

        still_missing = SaleItem.objects.filter(unit_cost=0, product__track_stock=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'{marked} expenses marked as stock purchases; cost added to {len(to_update)} sale lines.'
        ))
        if still_missing:
            self.stdout.write(self.style.WARNING(
                f'{still_missing} sale lines still have no cost (their products have no cost price yet).'
            ))