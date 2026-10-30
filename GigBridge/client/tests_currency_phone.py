from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from decimal import Decimal
from client.models import UserProfile, Project, Proposal, Contract, Milestone, ExchangeRate, Payment, ContactMessage, Category
from client.currency import (
    get_currency_for_country,
    get_usd_inr_rate,
    convert_inr_to_usd,
    convert_usd_to_inr,
    format_inr,
    format_usd,
    resolve_currency_for_user_or_request
)
from client.templatetags.currency_tags import (
    money_filter,
    contract_money,
    money_range
)
from client.forms import RegistrationForm, UserProfileForm, ContactForm, ProjectForm, ProposalForm


class CurrencyAndPhoneTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        # Seed initial exchange rate
        ExchangeRate.objects.update_or_create(
            from_currency='USD',
            to_currency='INR',
            defaults={'rate': Decimal('83.00')}
        )

        # Create Category for projects
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

    def test_currency_determination_for_country(self):
        """Rule: IN -> INR, others -> USD."""
        self.assertEqual(get_currency_for_country('IN'), 'INR')
        self.assertEqual(get_currency_for_country('in'), 'INR')
        self.assertEqual(get_currency_for_country('US'), 'USD')
        self.assertEqual(get_currency_for_country('GB'), 'USD')
        self.assertEqual(get_currency_for_country('AE'), 'USD')
        self.assertEqual(get_currency_for_country(''), 'USD')
        self.assertEqual(get_currency_for_country(None), 'USD')

    def test_user_profile_display_currency_sync(self):
        """UserProfile save() automatically keeps display_currency and full_phone in sync."""
        self.profile_in.refresh_from_db()
        self.assertEqual(self.profile_in.display_currency, 'INR')
        self.assertEqual(self.profile_in.full_phone, '+919876543210')

        self.profile_us.refresh_from_db()
        self.assertEqual(self.profile_us.display_currency, 'USD')
        self.assertEqual(self.profile_us.full_phone, '+12025550123')

    def test_guest_currency_resolution_and_cookie(self):
        """Guests can toggle currency via cookie, falling back to USD."""
        req = self.factory.get('/')
        self.assertEqual(resolve_currency_for_user_or_request(request=req), 'USD')

        req.COOKIES['gb_currency'] = 'INR'
        self.assertEqual(resolve_currency_for_user_or_request(request=req), 'INR')

        req.COOKIES['gb_currency'] = 'USD'
        self.assertEqual(resolve_currency_for_user_or_request(request=req), 'USD')

    def test_indian_and_usd_money_formatting(self):
        """Test Indian numbering formatting (₹1,25,000) and USD formatting ($1,500.00)."""
        amt = Decimal('125000')
        # INR format directly
        inr_str = format_inr(amt, include_symbol=True)
        self.assertEqual(inr_str, '₹1,25,000')

        # Filter with India user -> INR
        res_in = money_filter(amt, self.user_in)
        self.assertEqual(res_in, '₹1,25,000')

        # Filter with US user -> USD converted at 83.0
        # 125,000 / 83 = 1506.02
        res_us = money_filter(amt, self.user_us)
        self.assertEqual(res_us, '$1,506.02')

    def test_phone_number_validation_in_forms(self):
        """Server-side phonenumbers validation in RegistrationForm and ContactForm."""
        # Valid Indian phone
        data_valid_in = {
            'first_name': 'Rahul',
            'last_name': 'Patel',
            'username': 'newuser_in',
            'email': 'newin@example.com',
            'password1': 'Password123!',
            'password2': 'Password123!',
            'terms': True,
            'role': 'client',
            'country': 'IN',
            'phone_country_code': '+91',
            'phone_number': '9876543210',
            'phone': '9876543210',
        }
        form_in = RegistrationForm(data=data_valid_in)
        self.assertTrue(form_in.is_valid(), form_in.errors)

        # Invalid Indian phone (too short)
        data_invalid_in = dict(data_valid_in)
        data_invalid_in['phone_number'] = '1234'
        data_invalid_in['phone'] = '1234'
        form_bad_in = RegistrationForm(data=data_invalid_in)
        self.assertFalse(form_bad_in.is_valid())
        self.assertTrue('phone' in form_bad_in.errors or 'phone_number' in form_bad_in.errors)

        # Valid US phone in ContactForm
        contact_valid = {
            'name': 'John Doe',
            'email': 'john@example.com',
            'country': 'US',
            'phone': '202-555-0123',
            'subject': 'Inquiry',
            'message': 'Testing international telephone number parsing.',
        }
        cform = ContactForm(data=contact_valid)
        self.assertTrue(cform.is_valid(), cform.errors)
        cleaned_phone = cform.cleaned_data['phone']
        self.assertEqual(cleaned_phone, '+12025550123')

    def test_contract_currency_lock_preservation(self):
        """Contract locked exchange rate never changes when global exchange rate fluctuates."""
        project = Project.objects.create(
            client=self.user_us,
            title='Web Platform Project',
            description='Project description',
            budget_min=Decimal('83000'),
            budget_max=Decimal('83000'),
            budget_type='fixed',
            status='in_progress'
        )

        # Create contract locked at 83.00
        contract = Contract.objects.create(
            project=project,
            client=self.user_us,
            freelancer=self.freelancer_in,
            total_amount=Decimal('83000.00'), # 83,000 INR = 1,000 USD
            contract_currency='INR',
            exchange_rate_used=Decimal('83.00'),
            status='active'
        )
        milestone = Milestone.objects.create(
            contract=contract,
            order=1,
            title='Phase 1 Prototype',
            amount=Decimal('83000.00'),
            status='in_progress'
        )

        # Verify initial display for US client is $1,000.00
        initial_display = contract_money({}, contract, milestone.amount, self.user_us)
        self.assertEqual(initial_display, '$1,000.00')

        # Global rate shifts from 83.0 to 100.0
        ExchangeRate.objects.update_or_create(
            from_currency='USD',
            to_currency='INR',
            defaults={'rate': Decimal('100.00')}
        )

        # Fresh contract check must STILL use locked rate 83.00 ($1,000.00), NOT $830.00
        contract.refresh_from_db()
        locked_display = contract_money({}, contract, milestone.amount, self.user_us)
        self.assertEqual(locked_display, '$1,000.00')

    def test_price_entry_conversion_in_forms(self):
        """USD inputs are automatically converted to INR base amounts in forms."""
        # US client submits budget of $100.00 USD -> stored as 8,300.00 INR
        proj_form_data = {
            'title': 'API Microservice',
            'description': 'A detailed API specification for microservice endpoints.',
            'category': self.category.id,
            'budget_type': 'fixed',
            'status': 'open',
            'budget_min': '100.00', # USD
            'budget_max': '200.00', # USD
            'deadline': '2027-01-01',
            'experience_level': 'intermediate',
            'required_skills': 'Python, Django'
        }
        form = ProjectForm(data=proj_form_data, user=self.user_us)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['budget_min'], Decimal('8300.00'))
        self.assertEqual(form.cleaned_data['budget_max'], Decimal('16600.00'))
