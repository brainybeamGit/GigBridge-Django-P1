from decimal import Decimal
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

from client.models import (
    UserProfile, Category, Project, Proposal,
    Contract, Milestone, Submission, Payment, get_active_milestone
)


class SequentialMilestonesTests(TestCase):
    def setUp(self):
        # 1. Create client and freelancer users
        self.client_user = User.objects.create_user(
            username='client_test',
            email='client@example.com',
            password='testpassword123'
        )
        UserProfile.objects.get_or_create(user=self.client_user, defaults={'role': 'client'})

        self.freelancer_user = User.objects.create_user(
            username='freelancer_test',
            email='freelancer@example.com',
            password='testpassword123'
        )
        UserProfile.objects.get_or_create(user=self.freelancer_user, defaults={'role': 'freelancer'})

        # Other unrelated users for 403 tests
        self.other_client = User.objects.create_user(
            username='other_client',
            email='other_c@example.com',
            password='testpassword123'
        )
        UserProfile.objects.get_or_create(user=self.other_client, defaults={'role': 'client'})

        self.other_freelancer = User.objects.create_user(
            username='other_freelancer',
            email='other_f@example.com',
            password='testpassword123'
        )
        UserProfile.objects.get_or_create(user=self.other_freelancer, defaults={'role': 'freelancer'})

        # 2. Create Category and Project
        self.category = Category.objects.create(name='Web Development', slug='web-dev')
        self.project = Project.objects.create(
            client=self.client_user,
            title='Test Sequential Milestones Platform',
            description='Test project description for strict milestone ordering.',
            category=self.category,
            budget_type='fixed',
            budget_min=Decimal('400.00'),
            budget_max=Decimal('400.00'),
            deadline=timezone.now().date() + timedelta(days=60),
            status='in_progress',
        )

        # 3. Create Proposal
        self.proposal = Proposal.objects.create(
            project=self.project,
            freelancer=self.freelancer_user,
            bid_amount=Decimal('400.00'),
            cover_letter='High quality delivery assured.',
            delivery_days=30,
            status='accepted',
        )

        # 4. Create Contract with total 400
        self.contract = Contract.objects.create(
            project=self.project,
            proposal=self.proposal,
            client=self.client_user,
            freelancer=self.freelancer_user,
            total_amount=Decimal('400.00'),
            advance_amount=Decimal('100.00'),
            final_amount=Decimal('100.00'),
            status='active',
        )

        # 5. Create 3 Sequential Milestones:
        # Phase 1: Rs 100 (25%), Advance, Paid
        # Phase 2: Rs 200 (50%), Regular, In Progress
        # Phase 3: Rs 100 (25%), Final, Pending
        now = timezone.now().date()
        self.ms1 = Milestone.objects.create(
            contract=self.contract,
            title='Phase 1: Project Kickoff & Setup',
            milestone_type='advance',
            amount=Decimal('100.00'),
            order=1,
            due_date=now + timedelta(days=7),
            status='paid',
        )
        # Advance payment record for ms1
        Payment.objects.create(
            client=self.client_user,
            freelancer=self.freelancer_user,
            contract=self.contract,
            milestone=self.ms1,
            payment_type='advance',
            amount=Decimal('100.00'),
            status='completed',
            razorpay_payment_id='pay_test_advance_1',
            invoice_number='INV-TEST-0001',
        )

        self.ms2 = Milestone.objects.create(
            contract=self.contract,
            title='Phase 2: Core Development',
            milestone_type='regular',
            amount=Decimal('200.00'),
            order=2,
            due_date=now + timedelta(days=21),
            status='in_progress',
        )

        self.ms3 = Milestone.objects.create(
            contract=self.contract,
            title='Phase 3: Final Delivery & Deployment',
            milestone_type='final',
            amount=Decimal('100.00'),
            order=3,
            due_date=now + timedelta(days=35),
            status='pending',
        )

    def test_scenario_1_only_first_unpaid_milestone_is_active_and_cannot_submit_phase_3(self):
        """
        Scenario 1:
        Only the first unpaid milestone (Phase 2) is active.
        Submitting on Phase 3 while Phase 2 is unpaid must fail / be rejected.
        Submitting on Phase 2 succeeds.
        """
        self.assertEqual(get_active_milestone(self.contract).id, self.ms2.id)
        self.assertEqual(self.contract.get_active_milestone().id, self.ms2.id)
        self.assertTrue(self.ms2.is_active)
        self.assertFalse(self.ms3.is_active)
        self.assertTrue(self.ms3.is_locked)

        # Attempt submit on Phase 3 by freelancer
        client = Client()
        client.login(username='freelancer_test', password='testpassword123')

        url_submit_3 = reverse('freelancer_milestone_submit', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms3.id
        })
        response = client.post(url_submit_3, {
            'submission_notes': 'Trying to skip Phase 2 and submit Phase 3 directly.',
            'deliverable_link': 'https://github.com/test/project',
        }, follow=True)

        self.ms3.refresh_from_db()
        self.assertEqual(self.ms3.status, 'pending')
        self.assertEqual(self.ms3.submissions.count(), 0)

        # Now submit on the active milestone (Phase 2)
        url_submit_2 = reverse('freelancer_milestone_submit', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms2.id
        })
        response = client.post(url_submit_2, {
            'submission_notes': 'Phase 2 deliverables: backend models, serializers, and test suite.',
            'deliverable_link': 'https://github.com/test/project-phase2',
        }, follow=True)

        self.ms2.refresh_from_db()
        self.assertEqual(self.ms2.status, 'submitted')
        self.assertEqual(self.ms2.submissions.count(), 1)
        sub = self.ms2.submissions.first()
        self.assertIn('backend models', sub.submission_notes)

    def test_scenario_2_submit_approve_and_pay_phase_2_activates_phase_3(self):
        """
        Scenario 2:
        Freelancer submits Phase 2, client approves and pays Phase 2.
        Then Phase 2 becomes paid and Phase 3 automatically becomes in_progress.
        """
        # 1. Freelancer submits Phase 2
        f_client = Client()
        f_client.login(username='freelancer_test', password='testpassword123')
        url_submit = reverse('freelancer_milestone_submit', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms2.id
        })
        f_client.post(url_submit, {'submission_notes': 'Phase 2 implementation complete.'})

        self.ms2.refresh_from_db()
        self.assertEqual(self.ms2.status, 'submitted')
        self.assertTrue(self.ms2.can_approve(self.client_user))

        # 2. Client approves Phase 2
        c_client = Client()
        c_client.login(username='client_test', password='testpassword123')
        url_approve = reverse('client_contract_milestone_approve', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms2.id
        })
        resp_approve = c_client.post(url_approve, follow=True)
        self.assertEqual(resp_approve.status_code, 200)

        self.ms2.refresh_from_db()
        self.assertEqual(self.ms2.status, 'approved')
        self.assertTrue(self.ms2.can_pay(self.client_user))

        # 3. Client pays Phase 2 via payment verify endpoint
        url_verify = reverse('client_payment_verify')
        resp_verify = c_client.post(url_verify, {
            'milestone_id': self.ms2.id,
            'contract_id': self.contract.id,
            'payment_method': 'Razorpay Online',
            'ajax': '1',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp_verify.status_code, 200)

        self.ms2.refresh_from_db()
        self.ms3.refresh_from_db()
        self.assertEqual(self.ms2.status, 'paid')
        # Phase 3 must automatically transition to in_progress!
        self.assertEqual(self.ms3.status, 'in_progress')
        self.assertEqual(self.contract.get_active_milestone().id, self.ms3.id)

    def test_scenario_3_contract_is_not_completed_until_all_3_are_paid(self):
        """
        Scenario 3:
        Contract remains 'active' while Phase 1 and 2 are paid.
        Only transitions to 'completed' when the final Phase 3 is approved and paid.
        """
        # Pay Phase 2
        self.ms2.status = 'paid'
        self.ms2.save()
        Payment.objects.create(
            client=self.client_user,
            freelancer=self.freelancer_user,
            contract=self.contract,
            milestone=self.ms2,
            payment_type='regular',
            amount=Decimal('200.00'),
            status='completed',
            razorpay_payment_id='pay_test_phase_2',
            invoice_number='INV-TEST-0002',
        )
        self.ms3.status = 'in_progress'
        self.ms3.save()

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.status, 'active')
        self.assertFalse(self.contract.all_milestones_paid)

        # Submit and approve Phase 3
        self.ms3.status = 'submitted'
        self.ms3.submission_notes = 'Final package'
        self.ms3.save()

        c_client = Client()
        c_client.login(username='client_test', password='testpassword123')
        c_client.post(reverse('client_contract_milestone_approve', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms3.id
        }))

        # Pay Phase 3
        c_client.post(reverse('client_payment_verify'), {
            'milestone_id': self.ms3.id,
            'contract_id': self.contract.id,
            'payment_method': 'Razorpay Online',
            'ajax': '1',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.ms3.refresh_from_db()
        self.contract.refresh_from_db()
        self.assertEqual(self.ms3.status, 'paid')
        self.assertTrue(self.contract.all_milestones_paid)
        self.assertEqual(self.contract.status, 'completed')

    def test_scenario_4_idempotent_payment_creates_only_one_payment_and_invoice(self):
        """
        Scenario 4:
        Paying the same milestone twice creates only one payment and one invoice.
        """
        self.ms2.status = 'approved'
        self.ms2.save()

        c_client = Client()
        c_client.login(username='client_test', password='testpassword123')

        # First payment attempt
        resp1 = c_client.post(reverse('client_payment_verify'), {
            'milestone_id': self.ms2.id,
            'contract_id': self.contract.id,
            'payment_method': 'Razorpay Online',
            'ajax': '1',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(Payment.objects.filter(milestone=self.ms2).count(), 1)

        # Duplicate payment attempt for the same milestone
        resp2 = c_client.post(reverse('client_payment_verify'), {
            'milestone_id': self.ms2.id,
            'contract_id': self.contract.id,
            'payment_method': 'Razorpay Online',
            'ajax': '1',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp2.status_code, 200)

        # Count must remain exactly 1
        self.assertEqual(Payment.objects.filter(milestone=self.ms2).count(), 1)

    def test_scenario_5_unauthorized_user_gets_403(self):
        """
        Scenario 5:
        Client or freelancer from another contract gets 403 on submit, approve, revision, and pay.
        """
        other_f_client = Client()
        other_f_client.login(username='other_freelancer', password='testpassword123')

        # Other freelancer cannot submit deliverables
        url_submit = reverse('freelancer_milestone_submit', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms2.id
        })
        resp_f = other_f_client.post(url_submit, {'submission_notes': 'Hacker submission'})
        self.assertEqual(resp_f.status_code, 403)

        # Other client cannot approve or pay
        other_c_client = Client()
        other_c_client.login(username='other_client', password='testpassword123')

        self.ms2.status = 'submitted'
        self.ms2.save()

        url_approve = reverse('client_contract_milestone_approve', kwargs={
            'contract_id': self.contract.id,
            'milestone_id': self.ms2.id
        })
        resp_c = other_c_client.post(url_approve)
        self.assertEqual(resp_c.status_code, 403)

        url_verify = reverse('client_payment_verify')
        resp_p = other_c_client.post(url_verify, {
            'milestone_id': self.ms2.id,
            'contract_id': self.contract.id,
            'ajax': '1',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_p.status_code, 403)

    def test_scenario_6_progress_percentage_calculation(self):
        """
        Scenario 6:
        progress_percentage equals 25 with only Phase 1 paid (100 / 400 * 100),
        and 75 with Phase 2 also paid ( (100 + 200) / 400 * 100 = 75 ).
        100 with all 3 paid.
        """
        # Only Phase 1 is paid: 100 / 400 = 25%
        self.assertEqual(self.contract.paid_amount, Decimal('100.00'))
        self.assertEqual(self.contract.progress_percentage, 25)

        # Mark Phase 2 as paid: 100 + 200 = 300 / 400 = 75%
        self.ms2.status = 'paid'
        self.ms2.save()
        self.assertEqual(self.contract.paid_amount, Decimal('300.00'))
        self.assertEqual(self.contract.progress_percentage, 75)

        # Mark Phase 3 as paid: 300 + 100 = 400 / 400 = 100%
        self.ms3.status = 'paid'
        self.ms3.save()
        self.assertEqual(self.contract.paid_amount, Decimal('400.00'))
        self.assertEqual(self.contract.progress_percentage, 100)
