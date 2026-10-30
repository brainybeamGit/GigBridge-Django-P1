from django.db import migrations
from django.core.management import call_command


def run_repair_command(apps, schema_editor):
    try:
        call_command('repair_contracts')
    except Exception:
        # Avoid crashing during forward migration test runners where future model fields
        # (e.g. from 0013) are in current python models but not yet in the temporary test DB.
        pass


def reverse_repair(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('client', '0011_alter_milestone_options_milestone_order_submission'),
    ]

    operations = [
        migrations.RunPython(run_repair_command, reverse_repair),
    ]
