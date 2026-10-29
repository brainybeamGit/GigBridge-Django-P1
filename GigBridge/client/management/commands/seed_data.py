from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from client.models import Category, UserProfile


CATEGORIES = [
    ('Web Development', 'bi-code-slash', 'Full-stack, frontend, and backend web development projects.'),
    ('Mobile Apps', 'bi-phone', 'iOS, Android, and cross-platform mobile application development.'),
    ('UI/UX Design', 'bi-palette', 'User interface design, wireframes, prototypes, and design systems.'),
    ('Data Science & AI', 'bi-cpu', 'Machine learning, data analysis, AI models, and automation.'),
    ('Digital Marketing', 'bi-megaphone', 'SEO, social media, content marketing, and paid advertising.'),
    ('Writing & Content', 'bi-pencil-square', 'Blog posts, copywriting, technical writing, and content strategy.'),
    ('Video & Animation', 'bi-camera-video', 'Video editing, motion graphics, 2D/3D animation.'),
    ('Cybersecurity', 'bi-shield-lock', 'Penetration testing, security audits, and vulnerability assessments.'),
    ('DevOps & Cloud', 'bi-cloud-upload', 'CI/CD pipelines, Docker, Kubernetes, AWS, Azure, and GCP.'),
    ('Blockchain & Web3', 'bi-currency-bitcoin', 'Smart contracts, DeFi, NFTs, and decentralised applications.'),
    ('Game Development', 'bi-controller', 'Unity, Unreal Engine, 2D/3D game design and development.'),
    ('Finance & Accounting', 'bi-graph-up', 'Bookkeeping, financial modelling, tax, and business analysis.'),
]


class Command(BaseCommand):
    help = 'Seed the database with initial categories and a demo superuser.'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding categories...')
        for name, icon, desc in CATEGORIES:
            cat, created = Category.objects.get_or_create(
                name=name,
                defaults={'icon': icon, 'description': desc}
            )
            status = 'Created' if created else 'Already exists'
            self.stdout.write(f'  {status}: {name}')

        # Create a superuser for demo purposes if none exists
        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write('Creating demo superuser...')
            su = User.objects.create_superuser(
                username='admin',
                email='admin@gigbridge.com',
                password='admin123456',
                first_name='Admin',
                last_name='User',
            )
            UserProfile.objects.get_or_create(user=su, defaults={'role': 'admin'})
            self.stdout.write(self.style.SUCCESS('  Superuser created: admin / admin123456'))

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
