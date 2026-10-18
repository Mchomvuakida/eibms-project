import csv
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Branch, Product

VALID_CATEGORIES = {
    'raw_material', 'blocks', 'timber', 'pebbles', 'hardware',
    'electrical', 'plumbing', 'paint', 'tools',
}
TRUE_VALUES = {'true', '1', 'yes', 'y'}
UPDATE_FIELDS = [
    'category', 'unit', 'cost_price', 'selling_price',
    'current_stock', 'min_threshold', 'is_raw_material', 'is_active',
]


def clean_number(value):
    """Turn '55 000', '55,000', '1,5', '1.234,50' etc. into a Decimal. Blank -> None."""
    value = (value or '').strip().replace('\xa0', '').replace(' ', '')
    if value == '':
        return None
    if ',' in value and '.' in value:
        if value.rfind(',') > value.rfind('.'):
            value = value.replace('.', '').replace(',', '.')
        else:
            value = value.replace(',', '')
    elif ',' in value:
        head, _, tail = value.rpartition(',')
        if len(tail) == 3 and head.replace(',', '').isdigit():
            value = value.replace(',', '')
        else:
            value = value.replace(',', '.')
    return Decimal(value)


class Command(BaseCommand):
    help = 'Bulk import/update products from a CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str)

    def handle(self, *args, **options):
        path = options['csv_path']
        errors = []

        branch_cache = {b.name.lower(): b for b in Branch.objects.all()}
        existing = {(p.branch_id, p.name): p for p in Product.objects.all()}
        to_create = {}
        to_update = {}

        with open(path, newline='', encoding='utf-8-sig') as f:
            first_line = f.readline()
            f.seek(0)
            delimiter = ';' if first_line.count(';') > first_line.count(',') else ','
            reader = csv.DictReader(f, delimiter=delimiter)

            for i, row in enumerate(reader, start=2):
                name = (row.get('name') or '').strip()
                branch_name = (row.get('branch') or '').strip()
                category = (row.get('category') or '').strip()

                if not branch_name or not name or not category:
                    errors.append(f"Row {i} ({name or 'no name'}): missing branch, name, or category - skipped")
                    continue

                branch = branch_cache.get(branch_name.lower())
                if not branch:
                    errors.append(f"Row {i} ({name}): unknown branch '{branch_name}' - skipped")
                    continue

                if category not in VALID_CATEGORIES:
                    errors.append(f"Row {i} ({name}): invalid category '{category}' - skipped")
                    continue

                numbers = {}
                bad = None
                for col in ('cost_price', 'selling_price', 'current_stock', 'min_threshold'):
                    raw = row.get(col)
                    try:
                        numbers[col] = clean_number(raw)
                    except (InvalidOperation, ValueError):
                        bad = f"{col} = {raw!r}"
                        break
                if bad:
                    errors.append(f"Row {i} ({name}): cannot read number -> {bad} - skipped")
                    continue

                values = {
                    'category': category,
                    'unit': (row.get('unit') or '').strip(),
                    'cost_price': numbers['cost_price'],
                    'selling_price': numbers['selling_price'],
                    'current_stock': numbers['current_stock'] or Decimal('0'),
                    'min_threshold': numbers['min_threshold'] or Decimal('0'),
                    'is_raw_material': (row.get('is_raw_material') or '').strip().lower() in TRUE_VALUES,
                    'is_active': True,
                }

                key = (branch.id, name)
                if key in existing:
                    obj = existing[key]
                    for k, v in values.items():
                        setattr(obj, k, v)
                    to_update[key] = obj
                elif key in to_create:
                    obj = to_create[key]
                    for k, v in values.items():
                        setattr(obj, k, v)
                else:
                    to_create[key] = Product(branch=branch, name=name, **values)

        self.stdout.write(f'Read CSV: {len(to_create)} new, {len(to_update)} existing. Saving...')

        with transaction.atomic():
            Product.objects.bulk_create(list(to_create.values()), batch_size=200)
            Product.objects.bulk_update(list(to_update.values()), UPDATE_FIELDS, batch_size=200)

        self.stdout.write(self.style.SUCCESS(
            f'Done. {len(to_create)} products created, {len(to_update)} updated.'
        ))
        if errors:
            self.stdout.write(self.style.WARNING(f'{len(errors)} row(s) had problems:'))
            for err in errors:
                self.stdout.write(f'  - {err}')