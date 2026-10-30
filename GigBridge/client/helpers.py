"""
Security and permission helper functions for GigBridge messaging and access controls.
"""
from client.models import Proposal, Contract, Category, Project
from django.utils.text import slugify


def get_user_specialized_category(user):
    """
    Resolves the specialized Category for a user (client or freelancer) based on their profile.
    Priority:
    1. Direct match on UserProfile.title against Category.name (exact or case-insensitive)
    2. Slug match on UserProfile.title against Category.slug
    3. Keyword mapping for common industry specializations (e.g. AI & Machine Learning -> Data Science & AI)
    4. Substring / contains match between Category.name and title
    5. Category of the client's most recently posted project
    6. First available category in the database (fallback)
    """
    if not user or not user.is_authenticated:
        return None

    profile = getattr(user, 'profile', None)
    title = (getattr(profile, 'title', '') or '').strip()

    if title and title.lower() not in ['client / employer', 'client', 'employer']:
        # 1. Exact case-insensitive match
        cat = Category.objects.filter(name__iexact=title).first()
        if cat:
            return cat

        # 2. Slug match
        cat_slug = slugify(title)
        if cat_slug:
            cat = Category.objects.filter(slug=cat_slug).first()
            if cat:
                return cat

        # 3. Known industry specialization keyword mappings
        KEYWORD_MAPPINGS = [
            (('data science', 'machine learning', 'artificial intelligence', 'ai', 'deep learning'), 'Data Science & AI'),
            (('mobile', 'android', 'ios', 'flutter', 'react native', 'app dev', 'mobile app'), 'Mobile App Development'),
            (('ui/ux', 'ui / ux', 'ui design', 'ux design', 'product design', 'user experience'), 'UI/UX Design'),
            (('graphic design', 'illustration', 'branding', 'logo', 'photoshop', 'illustrator'), 'Graphic Design'),
            (('digital marketing', 'marketing', 'seo', 'social media', 'sem', 'growth marketing'), 'Digital Marketing'),
            (('content writing', 'writing', 'copywriting', 'media', 'blog', 'content creator'), 'Content Writing'),
            (('web development', 'web dev', 'full-stack', 'frontend', 'backend', 'django', 'python', 'react', 'web'), 'Web Development'),
        ]
        title_lower = title.lower()
        for keywords, target_cat_name in KEYWORD_MAPPINGS:
            for kw in keywords:
                if kw in title_lower:
                    matched = Category.objects.filter(name__iexact=target_cat_name).first()
                    if matched:
                        return matched

        # 4. Substring / contains match
        for cat in Category.objects.all():
            if cat.name.lower() in title_lower or title_lower in cat.name.lower():
                return cat

    # 5. Client's most recently posted project with a category
    last_project = Project.objects.filter(client=user, category__isnull=False).order_by('-created_at').first()
    if last_project and last_project.category:
        return last_project.category

    # 6. Fallback: first category in the database
    return Category.objects.order_by('name').first()


def can_message(user, project, other_user=None):
    """
    Rule: A freelancer and a client can message each other about a project
    ONLY when the freelancer's proposal on that project has status 'accepted'
    (or a contract exists for it).
    Pending, rejected, withdrawn, or no proposal means no message button and no chat access.
    """
    if not user or not user.is_authenticated or not project:
        return False

    if user.is_superuser:
        return True

    # 1. User is the project's client
    if project.client_id == user.id:
        if other_user:
            has_accepted = project.proposals.filter(freelancer=other_user, status='accepted').exists()
            has_contract = Contract.objects.filter(project=project, freelancer=other_user).exists()
            return bool(has_accepted or has_contract)
        else:
            return bool(project.proposals.filter(status='accepted').exists() or hasattr(project, 'contract'))

    # 2. User is a freelancer
    has_accepted = project.proposals.filter(freelancer=user, status='accepted').exists()
    has_contract = Contract.objects.filter(project=project, freelancer=user).exists()
    if not (has_accepted or has_contract):
        return False

    if other_user:
        return project.client_id == other_user.id

    return True


def can_message_conversation(user, conversation):
    """
    Verifies that the user is an authorized participant of the conversation
    and that the accepted-only messaging policy is satisfied.
    """
    if not user or not user.is_authenticated or not conversation:
        return False

    if user.is_superuser:
        return True

    # User must be part of conversation
    is_part = (
        conversation.client_id == user.id or
        conversation.freelancer_id == user.id or
        conversation.participants.filter(id=user.id).exists()
    )
    if not is_part:
        return False

    # Check project / proposal rule
    if conversation.project:
        other = conversation.get_other_participant(user)
        return can_message(user, conversation.project, other_user=other)
    elif conversation.proposal:
        return bool(conversation.proposal.status == 'accepted')

    return False
