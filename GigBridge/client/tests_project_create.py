from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from decimal import Decimal
from client.models import UserProfile, Category, Project
from client.helpers import get_user_specialized_category
from client.forms import ProjectForm


class ProjectCreateCategoryTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Categories
        self.cat_web = Category.objects.create(name='Web Development', slug='web-development')
        self.cat_ai = Category.objects.create(name='Data Science & AI', slug='data-science-ai')
        self.cat_mobile = Category.objects.create(name='Mobile App Development', slug='mobile-app-development')
        self.cat_design = Category.objects.create(name='UI/UX Design', slug='uiux-design')

        # Client 1: Specialized in Web Development
        self.client_web_user = User.objects.create_user(
            username='client_web',
            email='client_web@example.com',
            password='Password123!'
        )
        self.profile_web = UserProfile.objects.create(
            user=self.client_web_user,
            role='client',
            title='Web Development',
            is_approved=True
        )

        # Client 2: Specialized in AI & Machine Learning
        self.client_ai_user = User.objects.create_user(
            username='client_ai',
            email='client_ai@example.com',
            password='Password123!'
        )
        self.profile_ai = UserProfile.objects.create(
            user=self.client_ai_user,
            role='client',
            title='AI & Machine Learning',
            is_approved=True
        )

        # Client 3: Generic title with previous Mobile project
        self.client_prev_user = User.objects.create_user(
            username='client_prev',
            email='client_prev@example.com',
            password='Password123!'
        )
        self.profile_prev = UserProfile.objects.create(
            user=self.client_prev_user,
            role='client',
            title='Client / Employer',
            is_approved=True
        )
        Project.objects.create(
            client=self.client_prev_user,
            category=self.cat_mobile,
            title='Old Mobile App Project',
            description='Test project description here.',
            budget_type='fixed',
            budget_min=Decimal('500.00'),
            budget_max=Decimal('1000.00'),
            status='completed'
        )

    def test_helper_exact_category_match(self):
        """Helper correctly identifies exact category by user profile title."""
        matched = get_user_specialized_category(self.client_web_user)
        self.assertEqual(matched, self.cat_web)

    def test_helper_keyword_category_match(self):
        """Helper matches 'AI & Machine Learning' to 'Data Science & AI'."""
        matched = get_user_specialized_category(self.client_ai_user)
        self.assertEqual(matched, self.cat_ai)

    def test_helper_previous_project_fallback(self):
        """Helper falls back to category of previously posted project if title is generic."""
        matched = get_user_specialized_category(self.client_prev_user)
        self.assertEqual(matched, self.cat_mobile)

    def test_form_initial_category_preselected(self):
        """ProjectForm automatically sets initial category when user is passed."""
        form = ProjectForm(user=self.client_web_user)
        self.assertEqual(form.initial.get('category'), self.cat_web.pk)

    def test_project_create_page_renders_selected_category(self):
        """GET /client/projects/create/ pre-selects the client's Specialized Category."""
        self.client.login(username='client_web', password='Password123!')
        response = self.client.get(reverse('client_project_create'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('form', response.context)
        # Verify initial form field has the category id
        self.assertEqual(response.context['form'].initial.get('category'), self.cat_web.pk)
        # Verify the HTML option is marked selected
        expected_option = f'<option value="{self.cat_web.pk}" selected>Web Development</option>'
        self.assertContains(response, expected_option)

    def test_project_create_post_with_fallback(self):
        """If client posts project and category is omitted, client's specialized category is used."""
        self.client.login(username='client_web', password='Password123!')
        post_data = {
            'title': 'New Web Portal',
            'description': 'A detailed project description with required length.',
            'required_skills': 'Django, Python',
            'budget_type': 'fixed',
            'budget_min': '500.00',
            'budget_max': '1500.00',
            'status': 'open',
            'category': '',  # left blank
        }
        response = self.client.post(reverse('client_project_create'), data=post_data)
        self.assertEqual(response.status_code, 302)  # Redirects on success

        created_project = Project.objects.filter(title='New Web Portal').first()
        self.assertIsNotNone(created_project)
        self.assertEqual(created_project.category, self.cat_web)

    def test_project_create_post_with_custom_selection(self):
        """If client explicitly picks another category, their choice is saved."""
        self.client.login(username='client_web', password='Password123!')
        post_data = {
            'title': 'Cross-Domain Project',
            'description': 'A detailed project description with required length.',
            'required_skills': 'Figma, UI',
            'budget_type': 'fixed',
            'budget_min': '500.00',
            'budget_max': '1500.00',
            'status': 'open',
            'category': str(self.cat_design.pk),
        }
        response = self.client.post(reverse('client_project_create'), data=post_data)
        self.assertEqual(response.status_code, 302)

        created_project = Project.objects.filter(title='Cross-Domain Project').first()
        self.assertIsNotNone(created_project)
        self.assertEqual(created_project.category, self.cat_design)

    def test_project_create_with_image_upload(self):
        """Client can post a project with a custom cover image."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.login(username='client_web', password='Password123!')

        gif_bytes = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        uploaded_image = SimpleUploadedFile('cover_test.gif', gif_bytes, content_type='image/gif')

        post_data = {
            'title': 'Project with Custom Image',
            'description': 'A detailed project description with custom uploaded image.',
            'required_skills': 'Django, CSS',
            'budget_type': 'fixed',
            'budget_min': '800.00',
            'budget_max': '2000.00',
            'status': 'open',
            'category': str(self.cat_web.pk),
            'image': uploaded_image,
        }
        response = self.client.post(reverse('client_project_create'), data=post_data)
        self.assertEqual(response.status_code, 302)

        created_project = Project.objects.filter(title='Project with Custom Image').first()
        self.assertIsNotNone(created_project)
        self.assertTrue(bool(created_project.image))
        self.assertIn('cover_test', created_project.image.name)
        self.assertEqual(created_project.get_image_url, created_project.image.url)

    def test_project_without_image_uses_category_fallback(self):
        """If project has no uploaded image, get_image_url returns static fallback."""
        proj = Project.objects.create(
            client=self.client_web_user,
            category=self.cat_web,
            title='No Image Project',
            description='Test description.',
            budget_type='fixed',
            budget_min=Decimal('500.00'),
            budget_max=Decimal('1000.00'),
            status='open'
        )
        self.assertEqual(proj.get_image_url, '/static/images/project_ecommerce.jpg')

    def test_home_page_renders_project_card_image(self):
        """Home page displays the project image in the Featured Projects card."""
        proj = Project.objects.create(
            client=self.client_web_user,
            category=self.cat_web,
            title='Featured Home Test Project',
            description='Testing card rendering on the home page.',
            budget_type='fixed',
            budget_min=Decimal('500.00'),
            budget_max=Decimal('1000.00'),
            status='open'
        )
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Featured Home Test Project')
        self.assertContains(response, proj.get_image_url)

