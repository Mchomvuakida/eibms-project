from django.core.management.base import BaseCommand
from core.models import Expense

INCLUDE = ['ushuru', 'mchanga', 'mbao', 'kutoa', 'wapakiaji', 'wapkiaji', 'washusha',
           'washushaji', 'kushusha', 'kokoto', 'fundi aliyechana', 'saidia fundi',
           'trip', 'dereva posho']
EXCLUDE = ['wafyatuaji', 'mbanduaji', 'advance', 'ununuzi cement', 'cement 50bags',
           'diesel', 'gari', 'shamba']


class Command(BaseCommand):
    help = 'Move sand, timber, levy, hauling and loading costs into Cost of Sales'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually move them (without this, only a list is shown)')
        parser.add_argument('--skip', type=str, default='',
                            help='Comma-separated expense ids to leave alone')

    def handle(self, *args, **options):
        skip = {int(x) for x in options['skip'].split(',') if x.strip().isdigit()}
        candidates = Expense.objects.filter(
            category__in=['raw_materials', 'production_labor'],
            is_stock_purchase=False,
        ).select_related('branch').order_by('date')

        matches = []
        for e in candidates:
            text = (e.description or '').lower()
            if e.id in skip or any(w in text for w in EXCLUDE):
                continue
            if any(w in text for w in INCLUDE):
                matches.append(e)

        total = 0
        for e in matches:
            total += e.amount
            self.stdout.write(
                f"  id {e.id} | {e.date} | {e.branch.name} | {e.amount:,.0f} | {(e.description or '')[:60]}")
        self.stdout.write(f'\n{len(matches)} expenses, {total:,.0f} TZS would move to Cost of Sales.')

        if options['apply']:
            for e in matches:
                e.category = 'cost_of_sales'
                e.save(update_fields=['category'])
            self.stdout.write(self.style.SUCCESS('Done. They are now in Cost of Sales.'))
        else:
            self.stdout.write('Nothing was changed. Run again with --apply to move them.')