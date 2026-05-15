from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                password='Admin1234!',
                email='admin@eibms.com',
                role='admin'
            )
            self.stdout.write('Superuser created.')
        else:
            self.stdout.write('Superuser already exists.')