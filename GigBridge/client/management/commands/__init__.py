from django.core.management.base import BaseCommand
from client.management.commands.seed_data import Command as SeedCommand


class Command(SeedCommand):
    """Alias for seed_data."""
    pass
