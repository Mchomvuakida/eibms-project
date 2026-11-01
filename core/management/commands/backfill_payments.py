from django.core.management.base import BaseCommand
from core.models import Sale, Payment

VALID = ('cash', 'mobile_money', 'bank_transfer')


class Command(BaseCommand):
    help = 'Create payment records for sales made before payment records existed'

    def handle(self, *args, **options):
        done = set(Payment.objects.filter(kind='sale').values_list('sale_id', flat=True))
        new = []
        for sale in Sale.objects.filter(amount_paid__gt=0):
            if sale.id in done:
                continue
            new.append(Payment(
                branch_id=sale.branch_id, customer_id=sale.customer_id, sale=sale,
                amount=sale.amount_paid,
                method=sale.payment_method if sale.payment_method in VALID else 'cash',
                kind='sale', payment_date=sale.sale_date,
                received_by_id=sale.created_by_id,
                notes='Created from the sale record',
            ))
        Payment.objects.bulk_create(new, batch_size=200)
        self.stdout.write(self.style.SUCCESS(f'Created {len(new)} payment records.'))