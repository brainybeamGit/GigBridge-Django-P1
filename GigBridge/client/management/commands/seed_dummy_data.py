import os
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from client.models import (
    Category, UserProfile, Project, Proposal,
    Contract, Milestone, Payment, Review,
    Conversation, Message
)

class Command(BaseCommand):
    help = "Seed database with 1 Admin, 2 Clients, and 3 Freelancers, complete with projects, milestones, contracts, and reviews."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE("=== Starting GigBridge Dummy Data Seeding ==="))

        # ─── 0. Categories ───
        categories_data = [
            ('Web Development', 'bi-code-slash', 'Full-stack, frontend, and backend web development projects.'),
            ('Mobile App Development', 'bi-phone', 'iOS, Android, Flutter, and cross-platform mobile apps.'),
            ('DevOps & Cloud', 'bi-cloud-upload', 'CI/CD pipelines, Docker, Kubernetes, AWS, and GCP infrastructure.'),
            ('UI/UX Design', 'bi-palette', 'User interface design, wireframes, Figma prototypes, and design systems.'),
            ('Data Science & AI', 'bi-cpu', 'Machine learning, data analysis, Python AI models, and automation.'),
        ]
        cat_map = {}
        for name, icon, desc in categories_data:
            cat, _ = Category.objects.get_or_create(
                name=name,
                defaults={'icon': icon, 'description': desc}
            )
            cat_map[name] = cat

        # ─── 1. Admin Account (1) ───
        admin_user, _ = User.objects.get_or_create(
            username='admin123',
            defaults={
                'email': 'admin@gigbridge.com',
                'first_name': 'Platform',
                'last_name': 'Administrator',
                'is_staff': True,
                'is_superuser': True
            }
        )
        admin_user.set_password('Password123!')
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save()

        UserProfile.objects.update_or_create(
            user=admin_user,
            defaults={
                'role': 'admin',
                'title': 'Head of Platform Operations',
                'country': 'IN',
                'phone_country_code': '+91',
                'phone_number': '9876500000',
                'phone': '+919876500000',
                'display_currency': 'INR',
                'is_approved': True,
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Admin created/updated: admin123 (Password123!)"))

        # ─── 2. Client Accounts (2) ───
        # Client 1: US International Corporate Client
        client1_user, _ = User.objects.get_or_create(
            username='client1',
            defaults={
                'email': 'david.miller@techcorp.io',
                'first_name': 'David',
                'last_name': 'Miller',
            }
        )
        client1_user.first_name = 'David'
        client1_user.last_name = 'Miller'
        client1_user.email = 'david.miller@techcorp.io'
        client1_user.set_password('Password123!')
        client1_user.save()

        UserProfile.objects.update_or_create(
            user=client1_user,
            defaults={
                'role': 'client',
                'company_name': 'TechCorp Solutions Inc.',
                'title': 'VP of Engineering & Cloud Architecture',
                'bio': 'Leading digital transformation initiatives across North America. Building modern, scalable, and cloud-native solutions with verified engineering talent.',
                'country': 'US',
                'phone_country_code': '+1',
                'phone_number': '4155552671',
                'phone': '+14155552671',
                'display_currency': 'USD',
                'is_approved': True,
                'location': 'San Francisco, CA, USA'
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Client 1 created: client1 (David Miller - TechCorp Solutions, USD)"))

        # Client 2: India Enterprise Client
        client2_user, _ = User.objects.get_or_create(
            username='client2',
            defaults={
                'email': 'priya.sharma@innovatelabs.in',
                'first_name': 'Priya',
                'last_name': 'Sharma',
            }
        )
        client2_user.first_name = 'Priya'
        client2_user.last_name = 'Sharma'
        client2_user.email = 'priya.sharma@innovatelabs.in'
        client2_user.set_password('Password123!')
        client2_user.save()

        UserProfile.objects.update_or_create(
            user=client2_user,
            defaults={
                'role': 'client',
                'company_name': 'InnovateLabs Digital Pvt Ltd',
                'title': 'Director of Product Innovation',
                'bio': 'Spearheading product development and enterprise SaaS solutions in FinTech and HealthTech. Partnering with elite freelancers to build robust software systems.',
                'country': 'IN',
                'phone_country_code': '+91',
                'phone_number': '9820123456',
                'phone': '+919820123456',
                'display_currency': 'INR',
                'is_approved': True,
                'location': 'Mumbai, India'
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Client 2 created: client2 (Priya Sharma - InnovateLabs Digital, INR)"))

        # ─── 3. Freelancer Accounts (3) ───
        # Freelancer 1: Alex Rivera (Full-Stack & Python Architect - India)
        fl1_user, _ = User.objects.get_or_create(
            username='freelancer1',
            defaults={
                'email': 'alex.rivera@devbridge.com',
                'first_name': 'Alex',
                'last_name': 'Rivera',
            }
        )
        fl1_user.first_name = 'Alex'
        fl1_user.last_name = 'Rivera'
        fl1_user.email = 'alex.rivera@devbridge.com'
        fl1_user.set_password('Password123!')
        fl1_user.save()

        UserProfile.objects.update_or_create(
            user=fl1_user,
            defaults={
                'role': 'freelancer',
                'title': 'Lead Full-Stack Python & Django Architect',
                'bio': 'Specialized in architecting high-throughput Django REST APIs, PostgreSQL optimization, microservices, and modern React frontends. Test-driven and security-focused.',
                'skills': 'Python, Django, Django REST Framework, React, PostgreSQL, Docker, Redis, Celery, Git',
                'hourly_rate': Decimal('2500.00'),
                'country': 'IN',
                'phone_country_code': '+91',
                'phone_number': '9876543210',
                'phone': '+919876543210',
                'display_currency': 'INR',
                'is_approved': True,
                'location': 'Bengaluru, India',
                'average_rating': Decimal('5.0'),
                'total_reviews': 12,
                'completed_projects_count': 14,
                'on_time_delivery_rate': 98,
                'recommend_percentage': 100
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Freelancer 1 created: freelancer1 (Alex Rivera - Python Architect, INR)"))

        # Freelancer 2: Sarah Chen (Flutter & Mobile UI/UX - US)
        fl2_user, _ = User.objects.get_or_create(
            username='freelancer2',
            defaults={
                'email': 'sarah.chen@mobileworks.com',
                'first_name': 'Sarah',
                'last_name': 'Chen',
            }
        )
        fl2_user.first_name = 'Sarah'
        fl2_user.last_name = 'Chen'
        fl2_user.email = 'sarah.chen@mobileworks.com'
        fl2_user.set_password('Password123!')
        fl2_user.save()

        UserProfile.objects.update_or_create(
            user=fl2_user,
            defaults={
                'role': 'freelancer',
                'title': 'Senior Flutter & Mobile UI/UX Engineer',
                'bio': 'Crafting pixel-perfect cross-platform mobile apps for iOS and Android with Flutter & Dart. 6+ years shipping verified production apps with smooth 60fps animations.',
                'skills': 'Flutter, Dart, Firebase, iOS, Android, REST API Integration, UI/UX Design, Figma',
                'hourly_rate': Decimal('3320.00'), # ~$40 USD
                'country': 'US',
                'phone_country_code': '+1',
                'phone_number': '2125550198',
                'phone': '+12125550198',
                'display_currency': 'USD',
                'is_approved': True,
                'location': 'New York, NY, USA',
                'average_rating': Decimal('4.9'),
                'total_reviews': 9,
                'completed_projects_count': 11,
                'on_time_delivery_rate': 96,
                'recommend_percentage': 100
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Freelancer 2 created: freelancer2 (Sarah Chen - Flutter Specialist, USD)"))

        # Freelancer 3: Marcus Vance (Cloud Infrastructure & DevOps - India)
        fl3_user, _ = User.objects.get_or_create(
            username='freelancer3',
            defaults={
                'email': 'marcus.vance@cloudscale.net',
                'first_name': 'Marcus',
                'last_name': 'Vance',
            }
        )
        fl3_user.first_name = 'Marcus'
        fl3_user.last_name = 'Vance'
        fl3_user.email = 'marcus.vance@cloudscale.net'
        fl3_user.set_password('Password123!')
        fl3_user.save()

        UserProfile.objects.update_or_create(
            user=fl3_user,
            defaults={
                'role': 'freelancer',
                'title': 'DevOps & Cloud Systems Architect',
                'bio': 'Certified AWS Solutions Architect and Kubernetes Administrator. Expert in zero-downtime CI/CD pipelines, container orchestration, and multi-region infrastructure security.',
                'skills': 'AWS, Docker, Kubernetes, CI/CD, Terraform, Linux, PostgreSQL, Python, Bash, Grafana',
                'hourly_rate': Decimal('3000.00'),
                'country': 'IN',
                'phone_country_code': '+91',
                'phone_number': '9123456789',
                'phone': '+919123456789',
                'display_currency': 'INR',
                'is_approved': True,
                'location': 'Hyderabad, India',
                'average_rating': Decimal('5.0'),
                'total_reviews': 7,
                'completed_projects_count': 8,
                'on_time_delivery_rate': 100,
                'recommend_percentage': 100
            }
        )
        self.stdout.write(self.style.SUCCESS("[OK] Freelancer 3 created: freelancer3 (Marcus Vance - DevOps Architect, INR)"))

        # ─── 4. Seed Dynamic Projects ───
        # Project 1: Open Project by Client 1 (David Miller)
        p1, created = Project.objects.get_or_create(
            title='Cloud-Native Microservices Backend with Django & Docker',
            client=client1_user,
            defaults={
                'category': cat_map.get('Web Development'),
                'description': (
                    'TechCorp is looking for an expert full-stack engineer to design and develop '
                    'a resilient cloud-native microservices backend using Django, Django REST Framework, '
                    'PostgreSQL, Redis caching, and containerized Docker services. The application must feature '
                    'automated CI/CD pipelines, JWT authentication, and comprehensive unit tests.'
                ),
                'budget_type': 'fixed',
                'budget_min': Decimal('120000.00'), # ~$1,450 USD
                'budget_max': Decimal('200000.00'), # ~$2,400 USD
                'required_skills': 'Python, Django, Django REST Framework, PostgreSQL, Docker, Redis, Git',
                'deliverables': '1. Architecture & API Specifications, 2. Core Service Endpoints with Docker Compose, 3. Test Suite & Deployment Guide',
                'deadline': (timezone.now() + timedelta(days=25)).date(),
                'status': 'open',
                'views_count': 84
            }
        )
        self.stdout.write(f"  Project 1 ({p1.title[:40]}...): Status={p1.status}")

        # Project 2: Open Project by Client 2 (Priya Sharma)
        p2, created = Project.objects.get_or_create(
            title='Interactive Health & Fitness Tracking Mobile App in Flutter',
            client=client2_user,
            defaults={
                'category': cat_map.get('Mobile App Development'),
                'description': (
                    'InnovateLabs is commissioning a high-performance cross-platform Flutter application '
                    'for health metric visualization, real-time activity tracking, and meal scheduling. '
                    'Must include Firebase integration, offline data synchronization with SQLite/Hive, '
                    'and a modern responsive light-blue user experience.'
                ),
                'budget_type': 'fixed',
                'budget_min': Decimal('85000.00'),
                'budget_max': Decimal('150000.00'),
                'required_skills': 'Flutter, Dart, Firebase, UI/UX Design, REST API Integration, Android, iOS',
                'deliverables': '1. Figma UI Component Kit, 2. Core Flutter Activity Dashboard, 3. Final Production Build & App Store Assets',
                'deadline': (timezone.now() + timedelta(days=30)).date(),
                'status': 'open',
                'views_count': 112
            }
        )
        self.stdout.write(f"  Project 2 ({p2.title[:40]}...): Status={p2.status}")

        # Project 3: In-Progress Project & Contract by Client 1 with Freelancer 1
        p3, created = Project.objects.get_or_create(
            title='Automated Kubernetes CI/CD & Infrastructure as Code on AWS',
            client=client1_user,
            defaults={
                'category': cat_map.get('DevOps & Cloud'),
                'description': 'Provisioning scalable multi-AZ AWS EKS infrastructure with Terraform, GitHub Actions, and Prometheus monitoring.',
                'budget_type': 'fixed',
                'budget_min': Decimal('95000.00'),
                'budget_max': Decimal('140000.00'),
                'required_skills': 'AWS, Docker, Kubernetes, Terraform, CI/CD, Python',
                'deliverables': '1. Infrastructure Blueprint, 2. Terraform Scripts, 3. Cluster Deployment',
                'deadline': (timezone.now() + timedelta(days=14)).date(),
                'status': 'in_progress',
                'views_count': 65
            }
        )

        prop3, _ = Proposal.objects.get_or_create(
            project=p3,
            freelancer=fl3_user,
            defaults={
                'bid_amount': Decimal('120000.00'),
                'delivery_days': 14,
                'cover_letter': 'I have configured over 40 production AWS EKS clusters with Terraform and GitHub Actions. Ready to execute immediately with zero downtime.',
                'status': 'accepted'
            }
        )

        c3, _ = Contract.objects.get_or_create(
            project=p3,
            client=client1_user,
            freelancer=fl3_user,
            defaults={
                'proposal': prop3,
                'total_amount': Decimal('120000.00'),
                'advance_amount': Decimal('40000.00'),
                'final_amount': Decimal('80000.00'),
                'contract_currency': 'USD',
                'exchange_rate_used': Decimal('83.00'),
                'status': 'in_progress',
                'start_date': timezone.now().date() - timedelta(days=5),
            }
        )

        # Milestones for Contract 3
        m3_1, _ = Milestone.objects.get_or_create(
            contract=c3,
            order=1,
            defaults={
                'title': 'Milestone 1: Terraform Infrastructure Blueprints & AWS VPC Setup',
                'description': 'Deliver validated Terraform configuration for multi-AZ VPC, subnets, and IAM roles.',
                'amount': Decimal('40000.00'),
                'due_date': timezone.now().date() - timedelta(days=2),
                'status': 'approved',
                'submission_notes': 'Terraform files uploaded to Git repo and validated against AWS IAM policies.',
                'deliverable_link': 'https://github.com/techcorp/terraform-aws-vpc',
                'submitted_at': timezone.now() - timedelta(days=3),
                'approved_at': timezone.now() - timedelta(days=2),
            }
        )

        m3_2, _ = Milestone.objects.get_or_create(
            contract=c3,
            order=2,
            defaults={
                'title': 'Milestone 2: Kubernetes EKS Cluster & Prometheus Monitoring',
                'description': 'Deploy EKS cluster with helm charts for Prometheus, Grafana, and ingress controller.',
                'amount': Decimal('80000.00'),
                'due_date': timezone.now().date() + timedelta(days=9),
                'status': 'in_progress',
            }
        )
        self.stdout.write(f"  Contract 3 Active ({c3.project.title[:30]}...): In Progress (1 milestone paid)")

        # Project 4: Completed Project & Contract by Client 2 with Freelancer 2
        p4, created = Project.objects.get_or_create(
            title='FinTech Mobile Wallet UI Design & Cross-Platform Prototype',
            client=client2_user,
            defaults={
                'category': cat_map.get('UI/UX Design'),
                'description': 'Deliver interactive high-fidelity Figma components and responsive Flutter mobile prototype for FinTech transactions.',
                'budget_type': 'fixed',
                'budget_min': Decimal('75000.00'),
                'budget_max': Decimal('90000.00'),
                'required_skills': 'Flutter, UI/UX Design, Figma, Dart, Firebase',
                'deliverables': 'Complete Figma design system and functioning Flutter click-through prototype.',
                'deadline': timezone.now().date() - timedelta(days=10),
                'status': 'completed',
                'views_count': 95
            }
        )

        prop4, _ = Proposal.objects.get_or_create(
            project=p4,
            freelancer=fl2_user,
            defaults={
                'bid_amount': Decimal('85000.00'),
                'delivery_days': 10,
                'cover_letter': 'Excited to build your FinTech wallet interface! I specialize in clean typography, responsive graphs, and intuitive payments flows.',
                'status': 'accepted'
            }
        )

        c4, _ = Contract.objects.get_or_create(
            project=p4,
            client=client2_user,
            freelancer=fl2_user,
            defaults={
                'proposal': prop4,
                'total_amount': Decimal('85000.00'),
                'advance_amount': Decimal('25000.00'),
                'final_amount': Decimal('60000.00'),
                'contract_currency': 'INR',
                'exchange_rate_used': Decimal('83.00'),
                'status': 'completed',
                'start_date': timezone.now().date() - timedelta(days=20),
                'end_date': timezone.now().date() - timedelta(days=2),
            }
        )

        # Milestones for Completed Contract
        m4_1, _ = Milestone.objects.get_or_create(
            contract=c4,
            order=1,
            defaults={
                'title': 'Milestone 1: Design System & Figma Wireframes',
                'amount': Decimal('25000.00'),
                'status': 'approved',
                'submission_notes': 'Complete Figma design system with components, typography, and dark/light modes.',
                'deliverable_link': 'https://figma.com/@sarahchen/fintech-wallet-v1',
                'submitted_at': timezone.now() - timedelta(days=15),
                'approved_at': timezone.now() - timedelta(days=14),
            }
        )

        m4_2, _ = Milestone.objects.get_or_create(
            contract=c4,
            order=2,
            defaults={
                'title': 'Milestone 2: Flutter App Prototype & Final Handover',
                'amount': Decimal('60000.00'),
                'status': 'approved',
                'submission_notes': 'Interactive Flutter mobile application code repository with full documentation and test coverage.',
                'deliverable_link': 'https://github.com/innovatelabs/fintech-wallet-mobile',
                'submitted_at': timezone.now() - timedelta(days=4),
                'approved_at': timezone.now() - timedelta(days=2),
            }
        )

        # Review for Contract 4
        Review.objects.get_or_create(
            contract=c4,
            reviewer=client2_user,
            reviewee=fl2_user,
            defaults={
                'project': p4,
                'overall_rating': Decimal('5.0'),
                'rating': 5,
                'quality_of_work': 5,
                'communication': 5,
                'deadline_adherence': 5,
                'professionalism': 5,
                'comment': 'Outstanding execution! Sarah delivered our mobile UI on time, with exceptional attention to UX detail. Highly recommended for any Flutter or mobile design project.',
                'would_recommend': True,
                'tags': 'UI/UX, Flutter, On-Time, High Quality',
                'freelancer_reply': 'Thank you Priya! It was an absolute pleasure collaborating with InnovateLabs. Looking forward to our next project together.',
                'replied_at': timezone.now() - timedelta(days=1)
            }
        )
        self.stdout.write(f"  Contract 4 Completed ({c4.project.title[:30]}...): 5.0 Star Review and Escrow Fully Released")

        # ─── 5. Seed Conversations & Messages ───
        conv1, _ = Conversation.objects.get_or_create(
            project=p1,
            client=client1_user,
            freelancer=fl1_user,
        )
        if not conv1.messages.exists():
            Message.objects.create(
                conversation=conv1,
                sender=client1_user,
                content='Hi Alex, we reviewed your profile and past Django work. Can you tell us about your experience with Docker Compose and PostgreSQL connection pooling?'
            )
            Message.objects.create(
                conversation=conv1,
                sender=fl1_user,
                content='Hello David! Yes, absolutely. I implement PgBouncer for transaction-level pooling and use multi-stage Docker builds to keep image sizes under 150MB. I would be thrilled to submit a proposal for this project.'
            )

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Dummy data seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("---------------------------------------------------------------"))
        self.stdout.write(self.style.SUCCESS("All User Accounts Password: Password123!"))
        self.stdout.write(self.style.SUCCESS("Admin:       admin123     (admin@gigbridge.com)"))
        self.stdout.write(self.style.SUCCESS("Client 1:    client1      (david.miller@techcorp.io - USD)"))
        self.stdout.write(self.style.SUCCESS("Client 2:    client2      (priya.sharma@innovatelabs.in - INR)"))
        self.stdout.write(self.style.SUCCESS("Freelancer 1: freelancer1 (alex.rivera@devbridge.com - Python, INR)"))
        self.stdout.write(self.style.SUCCESS("Freelancer 2: freelancer2 (sarah.chen@mobileworks.com - Flutter, USD)"))
        self.stdout.write(self.style.SUCCESS("Freelancer 3: freelancer3 (marcus.vance@cloudscale.net - DevOps, INR)"))
        self.stdout.write(self.style.SUCCESS("---------------------------------------------------------------"))
