import csv
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from core.models import Branch, Product

VALID_CATEGORIES = {'raw_material', 'blocks', 'timber', 'pebbles', 'hardware'}
TRUE_VALUES = {'true', '1', 'yes', 'y'}


class Command(BaseCommand):
    help = 'Bulk import/update products from a CSV file (branch,name,category,unit,cost_price,selling_price,current_stock,min_threshold,is_raw_material)'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    def handle(self, *args, **options):
        path = options['csv_path']
        created_count = 0
        updated_count = 0
        errors = []

        branch_cache = {b.name.lower(): b for b in Branch.objects.all()}

        with open(path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, start=2):  # row 2 = first data row (1 is header)
                try:
                    branch_name = (row.get('branch') or '').strip()
                    name = (row.get('name') or '').strip()
                    category = (row.get('category') or '').strip()

                    if not branch_name or not name or not category:
                        errors.append(f"Row {i}: missing branch, name, or category — skipped")
                        continue

                    branch = branch_cache.get(branch_name.lower())
                    if not branch:
                        errors.append(f"Row {i}: unknown branch '{branch_name}' — skipped")
                        continue

                    if category not in VALID_CATEGORIES:
                        errors.append(f"Row {i}: invalid category '{category}' — skipped")
                        continue

                    def to_decimal(value):
                        value = (value or '').strip()
                        if value == '':
                            return None
                        return Decimal(value)

                    cost_price = to_decimal(row.get('cost_price'))
                    selling_price = to_decimal(row.get('selling_price'))
                    current_stock = to_decimal(row.get('current_stock')) or Decimal('0')
                    min_threshold = to_decimal(row.get('min_threshold')) or Decimal('0')
                    is_raw_material = (row.get('is_raw_material') or '').strip().lower() in TRUE_VALUES
                    unit = (row.get('unit') or '').strip()

                    obj, created = Product.objects.update_or_create(
                        branch=branch,
                        name=name,
                        defaults={
                            'category': category,
                            'unit': unit,
                            'cost_price': cost_price,
                            'selling_price': selling_price,
                            'current_stock': current_stock,
                            'min_threshold': min_threshold,
                            'is_raw_material': is_raw_material,
                            'is_active': True,
                        }
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except (InvalidOperation, ValueError) as e:
                    errors.append(f"Row {i}: bad number format — {e}")

        self.stdout.write(self.style.SUCCESS(
            f'Done. {created_count} products created, {updated_count} updated.'
        ))
        if errors:
            self.stdout.write(self.style.WARNING(f'{len(errors)} row(s) had problems:'))
            for err in errors:
                self.stdout.write(f'  - {err}')