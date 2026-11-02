import json
from decimal import Decimal
from django.test import TestCase, Client, RequestFactory
from django.contrib.auth.models import User
from django.urls import reverse
from django.conf import settings
from client.models import (
    UserProfile, Project, Proposal, Contract, Milestone,
    ExchangeRate, Payment, Category
)
from client.currency import (
    get_currency_for_country,
    get_usd_inr_rate,
    convert_inr_to_usd,
    convert_usd_to_inr,
    format_inr,
    format_usd,
    resolve_currency_for_user_or_request,
    set_current_request
)
from client.templatetags.currency_tags import (
    money_filter,
    contract_money,
    money_range_tag,
    currency_symbol_tag
)
from client.forms import RegistrationForm, ProjectForm


class ComprehensiveCurrencyAndPhoneTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

        # Seed initial exchange rate
        ExchangeRate.objects.update_or_create(
            from_currency='USD',
            to_currency='INR',
            defaults={'rate': Decimal('83.00')}
        )

        self.category = Category.objects.create(name='Web Development', slug='web-development')

        # Create Client user in India
        self.user_in = User.objects.create_user(
            username='client_india',
            email='client_in@example.com',
            password='Password123!'
        )
        self.profile_in = UserProfile.objects.create(
            user=self.user_in,
            role='client',
            country='IN',
            phone_country_code='+91',
            phone_number='9876543210'
        )

        # Create Client user in US
        self.user_us = User.objects.create_user(
            username='client_usa',
            email='client_us@example.com',
            password='Password123!'
        )
        self.profile_us = UserProfile.objects.create(
            user=self.user_us,
            role='client',
            country='US',
            phone_country_code='+1',
            phone_number='2025550123'
        )

        # Create Freelancer in India
        self.freelancer_in = User.objects.create_user(
            username='freelancer_in',
            email='freelancer_in@example.com',
            password='Password123!'
        )
        self.profile_fl = UserProfile.objects.create(
            user=self.freelancer_in,
            role='freelancer',
            country='IN',
            phone_country_code='+91',
            phone_number='9408986424',
            hourly_rate=Decimal('1000.00')
        )

    # 1. Country IN gives INR and every other country gives USD
    def test_country_currency_rule(self):
        """Rule: IN -> INR, any other country -> USD."""
        self.assertEqual(get_currency_for_country('IN'), 'INR')
        self.assertEqual(get_currency_for_country('in'), 'INR')
        self.assertEqual(get_currency_for_country('US'), 'USD')
        self.assertEqual(get_currency_for_country('GB'), 'USD')
        self.assertEqual(get_currency_for_country('AE'), 'USD')
        self.assertEqual(get_currency_for_country('CA'), 'USD')
        self.assertEqual(get_currency_for_country('AU'), 'USD')
        self.assertEqual(get_currency_for_country('DE'), 'USD')
        self.assertEqual(get_currency_for_country(''), 'USD')
        self.assertEqual(get_currency_for_country(None), 'USD')

        self.profile_in.refresh_from_db()
        self.assertEqual(self.profile_in.display_currency, 'INR')
        self.profile_us.refresh_from_db()
        self.assertEqual(self.profile_us.display_currency, 'USD')

    # 2. Money filter formatting for both
    def test_money_filter_formatting(self):
        """Indian formatting: ₹1,25,000 (no decimals for whole numbers). USD: $1,500.00 (2 decimals)."""
        amt = Decimal('125000')
        # INR Indian grouping
        inr_str = format_inr(amt, include_symbol=True)
        self.assertEqual(inr_str, '₹1,25,000')

        # US formatting with 83.0 rate: 125,000 / 83 = 1,506.02
        res_in = money_filter(amt, self.user_in)
        self.assertEqual(res_in, '₹1,25,000')

        res_us = money_filter(amt, self.user_us)
        self.assertEqual(res_us, '$1,506.02')

        # Thread-local request fallback
        req_in = self.factory.get('/')
        req_in.COOKIES['gb_currency'] = 'INR'
        set_current_request(req_in)
        self.assertEqual(money_filter(Decimal('5000')), '₹5,000')

        req_us = self.factory.get('/')
        req_us.COOKIES['gb_currency'] = 'USD'
        set_current_request(req_us)
        # 8300 INR / 83 = $100.00
        self.assertEqual(money_filter(Decimal('8300')), '$100.00')
        set_current_request(None)

    # 3. Phone validation for valid and invalid numbers in at least three countries
    def test_phone_validation_three_countries(self):
        """Validates phonenumbers for IN, US, and GB; rejects invalid numbers with clear messages."""
        base_data = {
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'terms': True,
            'role': 'client',
        }

        # Country 1: India (Valid & Invalid)
        data_in_valid = dict(base_data, username='u_in_valid', email='in_val@test.io', country='IN', phone='9876543210')
        f_in_v = RegistrationForm(data=data_in_valid)
        self.assertTrue(f_in_v.is_valid(), f_in_v.errors)
        self.assertEqual(f_in_v.cleaned_data['phone'], '+919876543210')

        data_in_invalid = dict(base_data, username='u_in_bad', email='in_bad@test.io', country='IN', phone='12345')
        f_in_b = RegistrationForm(data=data_in_invalid)
        self.assertFalse(f_in_b.is_valid())
        self.assertIn('India', str(f_in_b.errors.get('phone')))

        # Country 2: United States (Valid & Invalid)
        data_us_valid = dict(base_data, username='u_us_valid', email='us_val@test.io', country='US', phone='202-555-0123')
        f_us_v = RegistrationForm(data=data_us_valid)
        self.assertTrue(f_us_v.is_valid(), f_us_v.errors)
        self.assertEqual(f_us_v.cleaned_data['phone'], '+12025550123')

        data_us_invalid = dict(base_data, username='u_us_bad', email='us_bad@test.io', country='US', phone='999')
        f_us_b = RegistrationForm(data=data_us_invalid)
        self.assertFalse(f_us_b.is_valid())
        self.assertIn('United States', str(f_us_b.errors.get('phone')))

        # Country 3: United Kingdom (Valid & Invalid)
        data_gb_valid = dict(base_data, username='u_gb_valid', email='gb_val@test.io', country='GB', phone='07911 123456')
        f_gb_v = RegistrationForm(data=data_gb_valid)
        self.assertTrue(f_gb_v.is_valid(), f_gb_v.errors)
        self.assertEqual(f_gb_v.cleaned_data['phone'], '+447911123456')

        data_gb_invalid = dict(base_data, username='u_gb_bad', email='gb_bad@test.io', country='GB', phone='0123')
        f_gb_b = RegistrationForm(data=data_gb_invalid)
        self.assertFalse(f_gb_b.is_valid())
        self.assertIn('United Kingdom', str(f_gb_b.errors.get('phone')))

    # 4. Switch view (valid, invalid code, open redirect blocked, cookie set, profile updated)
    def test_currency_switch_view(self):
        """Tests /currency/switch/<code>/ handles cookie, profile sync, invalid codes, and open redirect protection."""
        self.client.login(username='client_india', password='Password123!')

        # Switch to USD
        url = reverse('currency_switch', kwargs={'code': 'USD'}) + '?next=/projects/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/projects/')
        self.assertEqual(response.cookies['gb_currency'].value, 'USD')
        self.assertIn('Cookie', response.headers.get('Vary', ''))

        self.profile_in.refresh_from_db()
        self.assertEqual(self.profile_in.display_currency, 'USD')

        # Invalid code falls back safely to INR
        url_bad = reverse('currency_switch', kwargs={'code': 'EUR'}) + '?next=/dashboard/'
        resp_bad = self.client.get(url_bad)
        self.assertEqual(resp_bad.status_code, 302)
        self.assertEqual(resp_bad.cookies['gb_currency'].value, 'INR')

        # Open redirect blocked
        url_hack = reverse('currency_switch', kwargs={'code': 'USD'}) + '?next=https://malicious-site.com/steal/'
        resp_hack = self.client.get(url_hack)
        self.assertEqual(resp_hack.status_code, 302)
        self.assertEqual(resp_hack.url, '/')  # Blocked to root!

    # 5. Budget filter conversion in both currencies
    def test_budget_filter_conversion_in_project_list(self):
        """Budget inputs entered in USD are converted to INR before querying Project.objects."""
        # Create project with budget 83,000 INR (~$1,000 USD)
        Project.objects.create(
            client=self.user_in,
            category=self.category,
            title='Django Currency Platform',
            description='Build multi-currency exchange platform.',
            budget_type='fixed',
            budget_min=Decimal('83000.00'),
            budget_max=Decimal('83000.00'),
            status='open'
        )

        # Set user display currency to USD
        self.client.login(username='client_usa', password='Password123!')

        # USD user filters min_budget=500 ($500 = ₹41,500 <= ₹83,000) -> Should find project
        url_match = reverse('project_list') + '?min_budget=500'
        res1 = self.client.get(url_match)
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, 'Django Currency Platform')

        # USD user filters min_budget=1500 ($1,500 = ₹124,500 > ₹83,000) -> Should NOT find project
        url_nomatch = reverse('project_list') + '?min_budget=1500'
        res2 = self.client.get(url_nomatch)
        self.assertEqual(res2.status_code, 200)
        self.assertNotContains(res2, 'Django Currency Platform')

    # 6. Contract rate staying locked
    def test_contract_rate_stays_locked(self):
        """Contract locked exchange rate never changes when global exchange rate changes."""
        project = Project.objects.create(
            client=self.user_us,
            title='Locked Exchange Milestone Contract',
            description='Description',
            budget_min=Decimal('83000'),
            budget_max=Decimal('83000'),
            budget_type='fixed',
            status='in_progress'
        )
        contract = Contract.objects.create(
            project=project,
            client=self.user_us,
            freelancer=self.freelancer_in,
            total_amount=Decimal('83000.00'), # 83,000 INR = $1,000 USD @ 83.0
            contract_currency='INR',
            exchange_rate_used=Decimal('83.00'),
            status='active'
        )
        milestone = Milestone.objects.create(
            contract=contract,
            order=1,
            title='Phase 1 Locked',
            amount=Decimal('83000.00'),
            status='in_progress'
        )

        initial = contract_money({}, contract, milestone.amount, self.user_us)
        self.assertEqual(initial, '$1,000.00')

        # Global rate shifts to 100.00
        ExchangeRate.objects.update_or_create(
            from_currency='USD',
            to_currency='INR',
            defaults={'rate': Decimal('100.00')}
        )

        contract.refresh_from_db()
        locked = contract_money({}, contract, milestone.amount, self.user_us)
        self.assertEqual(locked, '$1,000.00')

    # 7. Razorpay order amount in paise and cents
    def test_razorpay_order_amount_paise_and_cents(self):
        """Razorpay order amounts are computed in paise for INR and cents for USD."""
        project = Project.objects.create(
            client=self.user_us,
            title='Razorpay Order Test',
            description='Testing Razorpay order creation.',
            budget_min=Decimal('8300.00'),
            budget_max=Decimal('8300.00'),
            status='in_progress'
        )
        contract = Contract.objects.create(
            project=project,
            client=self.user_us,
            freelancer=self.freelancer_in,
            total_amount=Decimal('8300.00'),
            exchange_rate_used=Decimal('83.00'),
            status='active'
        )
        milestone = Milestone.objects.create(
            contract=contract,
            order=1,
            title='Phase 1 Initiation',
            amount=Decimal('8300.00'),
            status='in_progress'
        )

        self.client.login(username='client_usa', password='Password123!')

        # Order creation in default PAYMENT_CURRENCY='INR'
        url = reverse('client_payment_create_order')
        response = self.client.post(url, {'milestone_id': milestone.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['currency'], 'INR')
        self.assertEqual(data['amount'], 830000) # 8,300.00 INR = 830,000 paise
        self.assertIn('Charged in INR', data['charge_note'])

        # Now test PAYMENT_CURRENCY='USD'
        with self.settings(PAYMENT_CURRENCY='USD'):
            res_usd = self.client.post(url, {'milestone_id': milestone.id})
            self.assertEqual(res_usd.status_code, 200)
            data_usd = res_usd.json()
            self.assertEqual(data_usd['currency'], 'USD')
            # 8,300 INR / 83.0 = $100.00 -> 10,000 cents
            self.assertEqual(data_usd['amount'], 10000)
            self.assertIn('Charged in USD', data_usd['charge_note'])
