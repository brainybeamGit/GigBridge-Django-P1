from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.cache import cache
from decimal import Decimal
import requests
from client.models import ExchangeRate


class Command(BaseCommand):
    help = "Refreshes the USD to INR exchange rate from an external API with cached fallback."

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-rate',
            type=float,
            help='Manually specify an exchange rate (e.g. 84.50) without making an API call.'
        )

    def handle(self, *args, **options):
        force_rate = options.get('force_rate')
        if force_rate:
            rate_dec = Decimal(str(round(force_rate, 4)))
            obj, _ = ExchangeRate.objects.get_or_create(from_currency='USD', to_currency='INR')
            obj.rate = rate_dec
            obj.save()
            cache.set('usd_inr_rate', float(rate_dec), 86400)
            self.stdout.write(self.style.SUCCESS(f"Successfully set USD/INR exchange rate to {rate_dec}"))
            return

        api_urls = [
            "https://open.er-api.com/v6/latest/USD",
            "https://api.exchangerate-api.com/v4/latest/USD",
        ]

        rate = None
        for url in api_urls:
            try:
                resp = requests.get(url, timeout=4)
                if resp.status_code == 200:
                    data = resp.json()
                    inr = data.get('rates', {}).get('INR')
                    if inr and float(inr) > 0:
                        rate = Decimal(str(round(float(inr), 4)))
                        break
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Could not fetch rate from {url}: {e}"))

        if rate is not None:
            obj, _ = ExchangeRate.objects.get_or_create(from_currency='USD', to_currency='INR')
            obj.rate = rate
            obj.save()
            cache.set('usd_inr_rate', float(rate), 86400)
            self.stdout.write(self.style.SUCCESS(f"Successfully refreshed USD/INR rate to {rate} (1 USD = Rs. {rate} INR)"))
        else:
            fallback = getattr(settings, 'USD_INR_RATE', 83.0)
            fallback_dec = Decimal(str(fallback))
            obj, _ = ExchangeRate.objects.get_or_create(
                from_currency='USD',
                to_currency='INR',
                defaults={'rate': fallback_dec}
            )
            cache.set('usd_inr_rate', float(obj.rate), 3600)
            self.stdout.write(
                self.style.WARNING(
                    f"External API unreachable. Using fallback exchange rate: {obj.rate} (1 USD = Rs. {obj.rate} INR)"
                )
            )
