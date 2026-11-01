import csv
from decimal import InvalidOperation
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Product
from core.management.commands.import_products import clean_number


def fmt(value):
    if not value:
        return ''
    if value == value.to_integral_value():
        return str(int(value))
    return str(value).replace('.', ',')


class Command(BaseCommand):
    help = 'Export products to fill in cost prices, or import cost prices back (updates cost_price only)'

    def add_arguments(self, parser):
        parser.add_argument('mode', choices=['export', 'import'])
        parser.add_argument('csv_path')

    def handle(self, *args, **options):
        if options['mode'] == 'export':
            self.export(options['csv_path'])
        else:
            self.import_costs(options['csv_path'])

    def export(self, path):
        products = list(
            Product.objects.filter(is_active=True)
            .select_related('branch').order_by('branch__name', 'category', 'name')
        )
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';')
            w.writerow(['branch', 'name', 'category', 'unit', 'selling_price', 'cost_price'])
            for p in products:
                w.writerow([p.branch.name, p.name, p.category, p.unit,
                            fmt(p.selling_price), fmt(p.cost_price)])
        self.stdout.write(self.style.SUCCESS(f'Exported {len(products)} products to {path}'))

    def import_costs(self, path):
        products = {(p.branch.name.lower(), p.name): p
                    for p in Product.objects.select_related('branch')}
        updates, errors = [], []

        with open(path, newline='', encoding='utf-8-sig') as f:
            first = f.readline()
            f.seek(0)
            delim = ';' if first.count(';') > first.count(',') else ','
            for i, row in enumerate(csv.DictReader(f, delimiter=delim), start=2):
                key = ((row.get('branch') or '').strip().lower(), (row.get('name') or '').strip())
                product = products.get(key)
                if not product:
                    errors.append(f"Row {i}: product not found - {key[1]!r}")
                    continue
                try:
                    cost = clean_number(row.get('cost_price'))
                except (InvalidOperation, ValueError):
                    errors.append(f"Row {i} ({key[1]}): cannot read cost_price {row.get('cost_price')!r}")
                    continue
                if cost is None:
                    continue  # blank means leave unchanged
                product.cost_price = cost
                updates.append(product)

        with transaction.atomic():
            Product.objects.bulk_update(updates, ['cost_price'], batch_size=200)

        self.stdout.write(self.style.SUCCESS(f'Updated cost price on {len(updates)} products.'))
        for err in errors:
            self.stdout.write(self.style.WARNING('  - ' + err))