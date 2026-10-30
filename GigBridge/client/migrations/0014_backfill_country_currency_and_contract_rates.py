from django.db import migrations
from decimal import Decimal
import re


def backfill_data(apps, schema_editor):
    UserProfile = apps.get_model('client', 'UserProfile')
    Contract = apps.get_model('client', 'Contract')
    Payment = apps.get_model('client', 'Payment')
    ExchangeRate = apps.get_model('client', 'ExchangeRate')

    # Seed default USD to INR exchange rate
    ExchangeRate.objects.get_or_create(
        from_currency='USD',
        to_currency='INR',
        defaults={'rate': Decimal('83.0000')}
    )

    # Backfill UserProfile country, phone_country_code, phone_number, display_currency
    for profile in UserProfile.objects.all():
        raw_phone = (profile.phone or '').strip()
        digits = re.sub(r'\D', '', raw_phone)

        if raw_phone.startswith('+91') and len(digits) >= 12:
            profile.country = 'IN'
            profile.phone_country_code = '+91'
            profile.phone_number = digits[2:]
            profile.phone = f"+91{profile.phone_number}"
            profile.display_currency = 'INR'
        elif len(digits) == 10:
            profile.country = 'IN'
            profile.phone_country_code = '+91'
            profile.phone_number = digits
            profile.phone = f"+91{digits}"
            profile.display_currency = 'INR'
        elif raw_phone:
            # Fallback parse
            try:
                import phonenumbers
                parsed = phonenumbers.parse(raw_phone, 'IN')
                if phonenumbers.is_valid_number(parsed):
                    iso = phonenumbers.region_code_for_number(parsed) or 'IN'
                    profile.country = iso
                    profile.phone_country_code = f"+{parsed.country_code}"
                    profile.phone_number = str(parsed.national_number)
                    profile.phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    profile.display_currency = 'INR' if iso == 'IN' else 'USD'
                else:
                    profile.country = 'IN'
                    profile.phone_country_code = '+91'
                    profile.phone_number = ''
                    profile.display_currency = 'INR'
            except Exception:
                profile.country = 'IN'
                profile.phone_country_code = '+91'
                profile.phone_number = ''
                profile.display_currency = 'INR'
        else:
            profile.country = 'IN'
            profile.phone_country_code = '+91'
            profile.phone_number = ''
            profile.display_currency = 'INR'

        profile.save(update_fields=['country', 'phone_country_code', 'phone_number', 'phone', 'display_currency'])

    # Backfill Contracts
    for contract in Contract.objects.all():
        contract.contract_currency = 'INR'
        if not contract.exchange_rate_used or contract.exchange_rate_used <= Decimal('0'):
            contract.exchange_rate_used = Decimal('83.0000')
        contract.save(update_fields=['contract_currency', 'exchange_rate_used'])

    # Backfill Payments
    for payment in Payment.objects.all():
        if payment.base_amount_inr is None:
            payment.base_amount_inr = payment.amount
        if not payment.exchange_rate or payment.exchange_rate <= Decimal('0'):
            payment.exchange_rate = Decimal('83.0000')
        if not payment.currency:
            payment.currency = 'INR'
        payment.save(update_fields=['base_amount_inr', 'exchange_rate', 'currency'])


def reverse_data(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('client', '0013_contactmessage_phone_contract_contract_currency_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_data, reverse_data),
    ]
