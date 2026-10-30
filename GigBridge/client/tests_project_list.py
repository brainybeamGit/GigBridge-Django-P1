from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from client.models import UserProfile, Category, Project, Proposal, Bookmark
from client.templatetags.currency_tags import query_transform


class ProjectListAndBookmarksTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Category
        self.cat_web = Category.objects.create(name='Web Development', slug='web-development')
        self.cat_mobile = Category.objects.create(name='Mobile Development', slug='mobile-development')

        # Create Client user
        self.client_user = User.objects.create_user(
            username='tech_client',
            email='client@example.com',
            password='Password123!'
        )
        self.client_profile = UserProfile.objects.create(
            user=self.client_user,
            role='client',
            country='IN',
            is_approved=True
        )

        # Create Freelancer user
        self.freelancer_user = User.objects.create_user(
            username='pro_freelancer',
            email='freelancer@example.com',
            password='Password123!'
        )
        self.freelancer_profile = UserProfile.objects.create(
            user=self.freelancer_user,
            role='freelancer',
            country='IN'
        )

        # Create Projects
        self.proj1 = Project.objects.create(
            client=self.client_user,
            category=self.cat_web,
            title='Build a Django SaaS Platform',
            description='Looking for a Django and React full stack developer to build a modern SaaS.',
            budget_type='fixed',
            budget_min=Decimal('50000.00'),
            budget_max=Decimal('100000.00'),
            deadline=timezone.localdate() + timedelta(days=2), # closing soon
            required_skills='Python, Django, React',
            status='open'
        )

        self.proj2 = Project.objects.create(
            client=self.client_user,
            category=self.cat_mobile,
            title='Flutter iOS & Android Mobile App',
            description='Build a cross-platform Flutter application with Firebase backend.',
            budget_type='hourly',
            budget_min=Decimal('1000.00'),
            budget_max=Decimal('2500.00'),
            deadline=timezone.localdate() + timedelta(days=30),
            required_skills='Flutter, Dart, Firebase',
            status='open'
        )

        # Proposal on proj1
        Proposal.objects.create(
            project=self.proj1,
            freelancer=self.freelancer_user,
            bid_amount=Decimal('60000.00'),
            delivery_days=14,
            status='pending'
        )

    def test_project_list_view_renders_successfully(self):
        """Test GET /projects/ returns 200 and passes required context."""
        res = self.client.get(reverse('project_list'))
        self.assertEqual(res.status_code, 200)
        self.assertIn('page_obj', res.context)
        self.assertIn('categories', res.context)
        self.assertIn('total_results', res.context)
        self.assertIn('active_filters_count', res.context)
        self.assertIn('open_projects_count', res.context)
        self.assertEqual(res.context['total_results'], 2)

    def test_project_keyword_search(self):
        """Search by keyword in title or skills."""
        res = self.client.get(reverse('project_list') + '?q=Django')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_results'], 1)
        self.assertEqual(res.context['page_obj'][0].id, self.proj1.id)

    def test_project_category_filter(self):
        """Filter by category slug."""
        res = self.client.get(reverse('project_list') + '?category=mobile-development')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_results'], 1)
        self.assertEqual(res.context['page_obj'][0].id, self.proj2.id)

    def test_project_budget_type_filter(self):
        """Filter by budget_type ('fixed' vs 'hourly')."""
        res_fixed = self.client.get(reverse('project_list') + '?budget_type=fixed')
        self.assertEqual(res_fixed.context['total_results'], 1)
        self.assertEqual(res_fixed.context['page_obj'][0].id, self.proj1.id)

        res_hourly = self.client.get(reverse('project_list') + '?budget_type=hourly')
        self.assertEqual(res_hourly.context['total_results'], 1)
        self.assertEqual(res_hourly.context['page_obj'][0].id, self.proj2.id)

    def test_project_sorting(self):
        """Sort by budget_high and proposals."""
        res_sort_budget = self.client.get(reverse('project_list') + '?sort=budget_high')
        self.assertEqual(res_sort_budget.status_code, 200)
        self.assertEqual(res_sort_budget.context['page_obj'][0].id, self.proj1.id)

        res_sort_proposals = self.client.get(reverse('project_list') + '?sort=proposals')
        self.assertEqual(res_sort_proposals.status_code, 200)
        self.assertEqual(res_sort_proposals.context['page_obj'][0].id, self.proj1.id)

    def test_project_properties_is_new_and_closing_soon(self):
        """Verify is_new and is_closing_soon properties on Project."""
        self.assertTrue(self.proj1.is_new)
        self.assertTrue(self.proj1.is_closing_soon) # deadline is in 2 days
        self.assertFalse(self.proj2.is_closing_soon) # deadline is in 30 days

    def test_query_transform_template_tag(self):
        """Verify query_transform updates and removes parameters properly."""
        class DummyRequest:
            def __init__(self, query_string):
                from django.http import QueryDict
                self.GET = QueryDict(query_string, mutable=True)

        req = DummyRequest('q=python&category=web-dev&page=2')
        context = {'request': req}

        # Modify page
        out1 = query_transform(context, page=3)
        self.assertIn('page=3', out1)
        self.assertIn('q=python', out1)
        self.assertIn('category=web-dev', out1)

        # Remove category
        out2 = query_transform(context, category=None, page=None)
        self.assertNotIn('category', out2)
        self.assertNotIn('page', out2)
        self.assertEqual(out2, 'q=python')

    def test_bookmark_toggle_unauthenticated(self):
        """Unauthenticated user receives 401 when toggling bookmark."""
        res = self.client.post(reverse('project_bookmark_toggle', args=[self.proj1.id]))
        self.assertEqual(res.status_code, 401)
        data = res.json()
        self.assertEqual(data['status'], 'unauthenticated')
        self.assertIn('login_url', data)

    def test_bookmark_toggle_authenticated(self):
        """Authenticated user can bookmark and unbookmark a project."""
        self.client.force_login(self.freelancer_user)

        # 1. Bookmark project
        res1 = self.client.post(reverse('project_bookmark_toggle', args=[self.proj1.id]))
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1['status'], 'ok')
        self.assertTrue(data1['bookmarked'])
        self.assertEqual(data1['count'], 1)
        self.assertTrue(Bookmark.objects.filter(user=self.freelancer_user, project=self.proj1).exists())

        # Check project_list shows is_bookmarked=True
        res_list = self.client.get(reverse('project_list'))
        bookmarked_item = next(p for p in res_list.context['page_obj'] if p.id == self.proj1.id)
        self.assertTrue(bookmarked_item.is_bookmarked)

        # 2. Toggle again to unbookmark
        res2 = self.client.post(reverse('project_bookmark_toggle', args=[self.proj1.id]))
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2['status'], 'ok')
        self.assertFalse(data2['bookmarked'])
        self.assertEqual(data2['count'], 0)
        self.assertFalse(Bookmark.objects.filter(user=self.freelancer_user, project=self.proj1).exists())

    def test_saved_projects_view(self):
        """Verify saved_projects_view lists user's bookmarked projects."""
        self.client.force_login(self.freelancer_user)
        Bookmark.objects.create(user=self.freelancer_user, project=self.proj1)

        res = self.client.get(reverse('saved_projects'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['total_results'], 1)
        self.assertEqual(res.context['page_obj'][0].id, self.proj1.id)
