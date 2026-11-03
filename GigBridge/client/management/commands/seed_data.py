from django.core.management.base import BaseCommand
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Seed the database with initial categories, dummy accounts (1 admin, 2 clients, 3 freelancers), and sample activity.'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("Running master seed data command..."))
        call_command('seed_dummy_data')
        self.stdout.write(self.style.SUCCESS("All initial and dummy data seeded successfully!"))
