from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db.models import Avg, Count, Q
from django.conf import settings


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('client', 'Client / Employer'),
        ('freelancer', 'Freelancer'),
        ('admin', 'Administrator'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, blank=True, default='IN', help_text='ISO 2-letter country code (e.g. IN, US, GB)')
    phone_country_code = models.CharField(max_length=8, blank=True, default='+91', help_text='Dialing country code (e.g. +91, +1)')
    phone_number = models.CharField(max_length=20, blank=True, help_text='National phone number digits without country code')
    display_currency = models.CharField(
        max_length=3,
        choices=[('INR', 'Indian Rupee (₹)'), ('USD', 'US Dollar ($)')],
        default='INR',
        help_text="User's display currency"
    )
    company_name = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=150, blank=True, help_text='e.g. Full-Stack Developer or Product Manager')
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, default='Remote')
    skills = models.CharField(max_length=300, blank=True, help_text='Comma-separated skills')
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    website = models.URLField(blank=True)
    is_approved = models.BooleanField(
        default=True,
        help_text='Indicates if the client account has been verified and approved by the admin to post projects.'
    )

    # Dynamic aggregate fields on the freelancer profile
    average_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    total_reviews = models.PositiveIntegerField(default=0)
    avg_quality = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    avg_communication = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    avg_deadline = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    avg_professionalism = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    completed_projects_count = models.PositiveIntegerField(default=0)
    on_time_delivery_rate = models.PositiveIntegerField(default=100)
    repeat_clients_count = models.PositiveIntegerField(default=0)
    recommend_percentage = models.PositiveIntegerField(default=100)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def full_phone(self):
        if self.phone_country_code and self.phone_number:
            code = self.phone_country_code.strip()
            num = self.phone_number.strip()
            if not code.startswith('+'):
                code = '+' + code
            num = num.lstrip('0')
            return f"{code}{num}"
        return self.phone or ''

    def save(self, *args, **kwargs):
        if self.country:
            self.country = self.country.strip().upper()
            self.display_currency = 'INR' if self.country == 'IN' else 'USD'
        elif not self.display_currency:
            self.display_currency = 'INR'

        if self.phone_country_code and self.phone_number:
            self.phone = self.full_phone
        super().save(*args, **kwargs)

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()]

    @property
    def is_top_rated(self):
        """Top Rated when average_rating >= 4.7 and at least 5 reviews."""
        return self.average_rating >= Decimal('4.7') and self.total_reviews >= 5

    @property
    def is_rising_talent(self):
        """Rising Talent for new freelancers with at least 1 completed project and < 5 reviews."""
        return self.completed_projects_count >= 1 and self.total_reviews < 5

    @property
    def is_new_on_gigbridge(self):
        """New on GigBridge when there are no completed projects."""
        return self.completed_projects_count == 0

    @property
    def is_ontime_pro(self):
        """On-Time Pro when on_time_delivery_rate >= 90% and at least 1 completed project."""
        return self.on_time_delivery_rate >= 90 and self.completed_projects_count >= 1

    def recalculate_stats(self):
        """Recalculates all aggregate metrics from database records."""
        from client.models import Review, Contract

        # 1. Reviews aggregates (excluding hidden reviews)
        reviews = Review.objects.filter(reviewee=self.user, is_hidden=False)
        self.total_reviews = reviews.count()
        if self.total_reviews > 0:
            agg = reviews.aggregate(
                avg_overall=Avg('overall_rating'),
                avg_q=Avg('quality_of_work'),
                avg_c=Avg('communication'),
                avg_d=Avg('deadline_adherence'),
                avg_p=Avg('professionalism'),
                recommended=Count('id', filter=Q(would_recommend=True))
            )
            self.average_rating = Decimal(str(round(agg['avg_overall'] or 0.0, 1)))
            self.avg_quality = Decimal(str(round(agg['avg_q'] or 0.0, 1)))
            self.avg_communication = Decimal(str(round(agg['avg_c'] or 0.0, 1)))
            self.avg_deadline = Decimal(str(round(agg['avg_d'] or 0.0, 1)))
            self.avg_professionalism = Decimal(str(round(agg['avg_p'] or 0.0, 1)))
            rec_count = agg['recommended'] or 0
            self.recommend_percentage = round((rec_count / self.total_reviews) * 100)
        else:
            self.average_rating = Decimal('0.0')
            self.avg_quality = Decimal('0.0')
            self.avg_communication = Decimal('0.0')
            self.avg_deadline = Decimal('0.0')
            self.avg_professionalism = Decimal('0.0')
            self.recommend_percentage = 100

        # 2. Completed Contracts aggregates
        completed_contracts = Contract.objects.filter(freelancer=self.user, status='completed')
        self.completed_projects_count = completed_contracts.count()

        # Repeat clients: distinct clients with > 1 completed contract with this freelancer
        repeat_clients = (
            completed_contracts.values('client')
            .annotate(c_count=Count('id'))
            .filter(c_count__gt=1)
            .count()
        )
        self.repeat_clients_count = repeat_clients

        # On-time delivery rate
        contracts_with_deadline = [
            c for c in completed_contracts.select_related('project')
            if c.project and c.project.deadline and c.end_date
        ]
        if contracts_with_deadline:
            on_time = sum(1 for c in contracts_with_deadline if c.end_date.date() <= c.project.deadline)
            self.on_time_delivery_rate = round((on_time / len(contracts_with_deadline)) * 100)
        else:
            self.on_time_delivery_rate = 100 if self.completed_projects_count > 0 else 0

        self.save(update_fields=[
            'average_rating', 'total_reviews',
            'avg_quality', 'avg_communication', 'avg_deadline', 'avg_professionalism',
            'completed_projects_count', 'on_time_delivery_rate', 'repeat_clients_count',
            'recommend_percentage'
        ])


class ExchangeRate(models.Model):
    from_currency = models.CharField(max_length=3, default='USD')
    to_currency = models.CharField(max_length=3, default='INR')
    rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('83.0000'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('from_currency', 'to_currency')

    def __str__(self):
        return f"1 {self.from_currency} = {self.rate} {self.to_currency}"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(max_length=50, default='bi-briefcase', help_text='Bootstrap icon class')
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def project_count(self):
        return self.projects.filter(status='open').count()


class Project(models.Model):
    BUDGET_TYPE_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly Rate'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('open', 'Open for Bidding'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_projects')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='projects')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField()
    budget_type = models.CharField(max_length=10, choices=BUDGET_TYPE_CHOICES, default='fixed')
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deadline = models.DateField(blank=True, null=True)
    required_skills = models.CharField(max_length=300, help_text='Comma-separated skills, e.g. Python, Django, React')
    deliverables = models.TextField(blank=True, help_text='Key deliverables and project expectations')
    attachment = models.FileField(upload_to='project_files/', blank=True, null=True)
    image = models.ImageField(upload_to='project_images/', blank=True, null=True, help_text='Project featured/cover image')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def skills_list(self):
        return [s.strip() for s in self.required_skills.split(',') if s.strip()]

    @property
    def get_image_url(self):
        """Returns the project image URL if uploaded, or a fallback category/default image."""
        if self.image:
            try:
                return self.image.url
            except Exception:
                pass
        slug = self.category.slug if self.category else ''
        if 'ecommerce' in slug or 'web' in slug:
            return '/static/images/project_ecommerce.jpg'
        elif 'marketing' in slug or 'seo' in slug:
            return '/static/images/project_marketing.jpg'
        elif 'content' in slug or 'writing' in slug:
            return '/static/images/project_seo_blog.jpg'
        elif 'design' in slug or 'logo' in slug or 'ui' in slug or 'graphic' in slug:
            return '/static/images/project_logo.jpg'
        return '/static/images/project_ecommerce.jpg'

    @property
    def proposals_count(self):
        if hasattr(self, '_proposals_count'):
            return self._proposals_count
        return self.proposals.count()

    @proposals_count.setter
    def proposals_count(self, value):
        self._proposals_count = value

    @property
    def prop_count(self):
        return self.proposals.count()

    @property
    def pending_proposals_count(self):
        return self.proposals.filter(status='pending').count()

    @property
    def is_new(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.created_at:
            return False
        return timezone.now() - self.created_at <= timedelta(hours=48)

    @property
    def is_closing_soon(self):
        from django.utils import timezone
        from datetime import timedelta
        if self.deadline and self.status == 'open':
            today = timezone.localdate()
            return today <= self.deadline <= today + timedelta(days=3)
        return False


class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookmarks')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='bookmarks')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'project')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} saved {self.project.title}"


class Proposal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='proposals')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='proposals_submitted')
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_days = models.PositiveIntegerField(default=7, help_text='Estimated delivery days')
    cover_letter = models.TextField()
    attachment = models.FileField(upload_to='proposal_files/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('project', 'freelancer')

    def __str__(self):
        return f"Proposal by {self.freelancer.username} for '{self.project.title}'"


class Contract(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='contract')
    proposal = models.OneToOneField(Proposal, on_delete=models.SET_NULL, null=True, blank=True, related_name='contract')
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_contracts')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='freelancer_contracts')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Agreed advance payment amount")
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Remaining final payment after full delivery")
    deliverables = models.TextField(blank=True, help_text="Key deliverables and specifications agreed in contract")
    contract_currency = models.CharField(max_length=3, default='INR', help_text="Base currency for contract accounting")
    exchange_rate_used = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('83.0000'),
        help_text="USD to INR rate locked at contract creation"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Contract: {self.project.title}"

    def get_amount_for_currency(self, amount_in_inr, target_currency='INR'):
        if amount_in_inr is None:
            return Decimal('0.00')
        from decimal import ROUND_HALF_UP
        amt = Decimal(str(amount_in_inr))
        if target_currency == 'USD':
            rate = self.exchange_rate_used or Decimal('83.0000')
            if rate <= Decimal('0'):
                rate = Decimal('83.0000')
            return (amt / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return amt

    @property
    def paid_amount(self):
        paid = self.milestones.filter(status='paid').aggregate(models.Sum('amount'))['amount__sum']
        if paid is None:
            paid = self.payments.filter(status='completed').aggregate(models.Sum('amount'))['amount__sum']
        return paid or Decimal('0.00')

    @property
    def remaining_amount(self):
        total = self.total_amount or Decimal('0.00')
        paid = self.paid_amount
        return max(Decimal('0.00'), total - paid)

    @property
    def escrow_secured_amount(self):
        """Total funds secured in escrow or paid."""
        paid_or_escrow = self.milestones.filter(status__in=['paid', 'approved', 'submitted', 'in_progress']).aggregate(models.Sum('amount'))['amount__sum']
        return paid_or_escrow or Decimal('0.00')

    @property
    def advance_milestone(self):
        return self.milestones.filter(milestone_type='advance').order_by('order', 'id').first() or self.milestones.order_by('order', 'id').first()

    @property
    def final_milestone(self):
        return self.milestones.filter(milestone_type='final').order_by('-order', '-id').first() or self.milestones.order_by('-order', '-id').first()

    @property
    def is_advance_paid(self):
        adv = self.advance_milestone
        return bool(adv and adv.status == 'paid')

    @property
    def can_start_work(self):
        adv = self.advance_milestone
        return bool(not adv or adv.status == 'paid')

    def get_active_milestone(self):
        """
        Returns the single active milestone: the first milestone in order that is not paid.
        If all milestones are paid, returns None.
        """
        return self.milestones.exclude(status='paid').order_by('order', 'id').first()

    @property
    def active_milestone(self):
        return self.get_active_milestone()

    @property
    def all_milestones_paid(self):
        return bool(self.milestones.exists() and not self.milestones.exclude(status='paid').exists())

    @property
    def progress_percentage(self):
        """
        Calculated as: sum of paid milestone amounts / total contract amount * 100.
        """
        if self.status == 'completed' or self.all_milestones_paid:
            return 100
        total = self.total_amount
        if not total or total <= Decimal('0.00'):
            return 0
        paid = self.milestones.filter(status='paid').aggregate(models.Sum('amount'))['amount__sum'] or Decimal('0.00')
        return int(round((paid / total) * 100))

    @property
    def next_payment_due_milestone(self):
        return self.get_active_milestone()




def get_active_milestone(contract):
    """Module-level helper returning the single active milestone for a contract."""
    if not contract:
        return None
    return contract.get_active_milestone()


class Milestone(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('submitted', 'Work Submitted'),
        ('revision_requested', 'Revision Requested'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ]
    TYPE_CHOICES = [
        ('advance', 'Advance Payment'),
        ('final', 'Final Delivery & Completion'),
        ('regular', 'Milestone'),
    ]

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='milestones')
    order = models.PositiveIntegerField(default=1, help_text="Sequential milestone order (1, 2, 3...)")
    milestone_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='regular')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='pending')
    submission_notes = models.TextField(blank=True)
    deliverable_link = models.URLField(blank=True, help_text="Git repository or live demo preview link")
    submission_file = models.FileField(upload_to='milestone_files/', blank=True, null=True)
    revision_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Phase {self.order}: {self.title} ({self.contract.project.title})"

    def clean(self):
        super().clean()
        if self.contract_id and self.due_date and self.order:
            earlier = self.contract.milestones.filter(order__lt=self.order, due_date__isnull=False).order_by('-order').first()
            if earlier and earlier.due_date and self.due_date < earlier.due_date:
                from django.core.exceptions import ValidationError
                raise ValidationError({
                    'due_date': f"Due date ({self.due_date}) cannot be earlier than previous milestone's due date ({earlier.due_date})."
                })

    @property
    def is_active(self):
        """True if this milestone is the active (first unpaid) milestone of the contract."""
        active = self.contract.get_active_milestone()
        return bool(active and active.id == self.id)

    @property
    def previous_milestone(self):
        """Returns the milestone immediately preceding this one in the contract order."""
        return self.contract.milestones.filter(order__lt=self.order).order_by('-order', '-id').first()

    @property
    def is_locked(self):
        """
        Locked if any previous milestone in the contract order is not paid.
        """
        return self.contract.milestones.filter(order__lt=self.order).exclude(status='paid').exists()

    def can_submit(self, user=None):
        """
        Freelancer can submit work only when:
        - The milestone is the contract's active milestone
        - Status is 'in_progress' or 'revision_requested'
        - If user provided, user is the contract's freelancer or superuser
        """
        if user and not user.is_superuser and user != self.contract.freelancer:
            return False
        if not self.is_active:
            return False
        return self.status in ['in_progress', 'revision_requested']

    def can_approve(self, user=None):
        """
        Client can approve only when:
        - The milestone is the contract's active milestone
        - Status is 'submitted'
        - If user provided, user is the contract's client or superuser
        """
        if user and not user.is_superuser and user != self.contract.client:
            return False
        if not self.is_active:
            return False
        return self.status == 'submitted'

    def can_request_revision(self, user=None):
        """
        Client can request revision only when:
        - The milestone is the contract's active milestone
        - Status is 'submitted' (or 'approved')
        - If user provided, user is the contract's client or superuser
        """
        if user and not user.is_superuser and user != self.contract.client:
            return False
        if not self.is_active:
            return False
        return self.status in ['submitted', 'approved']

    def can_pay(self, user=None):
        """
        Client can pay this milestone only when:
        - The milestone is the contract's active milestone
        - Status is not 'paid'
        - All earlier milestones are paid
        - Either:
          - It is an advance payment milestone (milestone_type='advance' or order==1) and status in ['pending', 'in_progress']
          - OR status is 'approved'
        - If user provided, user is the contract's client or superuser
        """
        if user and not user.is_superuser and user != self.contract.client:
            return False
        if not self.is_active:
            return False
        if self.status == 'paid':
            return False
        if self.is_locked:
            return False
        if self.milestone_type == 'advance' or self.order == 1:
            return self.status in ['pending', 'in_progress']
        return self.status == 'approved'

    @property
    def latest_submission(self):
        return self.submissions.order_by('-created_at').first()


class Submission(models.Model):
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name='submissions')
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='submissions')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submissions')
    submission_notes = models.TextField(blank=True)
    deliverable_link = models.URLField(blank=True, help_text="Git repository or live demo preview link")
    submission_file = models.FileField(upload_to='milestone_files/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Submission for {self.milestone.title} ({self.created_at.strftime('%Y-%m-%d %H:%M')})" 


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]
    PAYMENT_TYPE_CHOICES = [
        ('advance', 'Advance Payment'),
        ('final', 'Final Payment'),
        ('milestone', 'Milestone Payment'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_made')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments_received')
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='payments')
    milestone = models.ForeignKey(Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='milestone')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    base_amount_inr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Base amount in INR")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('83.0000'), help_text="Exchange rate at payment")
    payment_method = models.CharField(max_length=50, default='Razorpay Test Mode')
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.invoice_number} - {self.amount} {self.currency}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            import uuid
            self.invoice_number = f"GB-{timezone.now().strftime('%Y%m')}-{str(uuid.uuid4())[:8].upper()}"
        super().save(*args, **kwargs)


class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='conversations')
    client = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='client_conversations')
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='freelancer_conversations')
    proposal = models.ForeignKey('Proposal', on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = ('project', 'client', 'freelancer')

    def __str__(self):
        proj_title = self.project.title if self.project else 'General'
        client_name = self.client.username if self.client else 'Client'
        freelancer_name = self.freelancer.username if self.freelancer else 'Freelancer'
        return f"Conversation #{self.id}: {client_name} & {freelancer_name} ({proj_title})"

    def get_other_participant(self, user=None):
        if user and hasattr(user, 'id'):
            if self.client and self.freelancer:
                return self.freelancer if user.id == self.client_id else self.client
            return self.participants.exclude(id=user.id).first()
        return self.freelancer or self.participants.first()

    def unread_count_for(self, user=None):
        if user and hasattr(user, 'id'):
            return self.messages.filter(is_read=False).exclude(sender=user).count()
        return self.messages.filter(is_read=False).count()

    @classmethod
    def get_or_create_conversation(cls, client, freelancer, project=None, proposal=None):
        if client == freelancer:
            return None, False

        # Normalize client vs freelancer
        client_user = client
        freelancer_user = freelancer
        if project and project.client:
            if freelancer == project.client:
                client_user, freelancer_user = freelancer, client
            else:
                client_user = project.client
                freelancer_user = freelancer if freelancer != client_user else client

        if not proposal and project:
            proposal = project.proposals.filter(freelancer=freelancer_user, status='accepted').first()

        qs = cls.objects.filter(project=project, client=client_user, freelancer=freelancer_user)
        conv = qs.first()
        if not conv:
            conv = cls.objects.filter(participants=client_user).filter(participants=freelancer_user)
            if project:
                conv = conv.filter(project=project)
            conv = conv.first()

        if conv:
            updated = False
            if not conv.client:
                conv.client = client_user
                updated = True
            if not conv.freelancer:
                conv.freelancer = freelancer_user
                updated = True
            if project and not conv.project:
                conv.project = project
                updated = True
            if proposal and not conv.proposal:
                conv.proposal = proposal
                updated = True
            if not conv.participants.filter(id=client_user.id).exists():
                conv.participants.add(client_user)
            if not conv.participants.filter(id=freelancer_user.id).exists():
                conv.participants.add(freelancer_user)
            if updated:
                conv.save()
            return conv, False

        conv = cls.objects.create(
            project=project,
            client=client_user,
            freelancer=freelancer_user,
            proposal=proposal
        )
        conv.participants.add(client_user, freelancer_user)
        return conv, True


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    content = models.TextField()
    attachment = models.FileField(upload_to='message_attachments/', blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender.username} at {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def body(self):
        return self.content

    @body.setter
    def body(self, value):
        self.content = value


class Review(models.Model):
    RATING_CHOICES = [
        (5, '5 Stars - Exceptional'),
        (4, '4 Stars - Very Good'),
        (3, '3 Stars - Good'),
        (2, '2 Stars - Fair'),
        (1, '1 Star - Poor'),
    ]

    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name='review')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    reviewee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reviews')

    # Category ratings, each 1 to 5
    quality_of_work = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    communication = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    deadline_adherence = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")
    professionalism = models.PositiveSmallIntegerField(default=5, help_text="Rating 1-5")

    # overall_rating: calculated automatically as the average of the 4 categories, rounded to 1 decimal
    overall_rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    rating = models.PositiveSmallIntegerField(default=5)  # Backwards compatibility integer rating

    comment = models.TextField(help_text="Detailed review (min 20, max 1000 chars)")
    would_recommend = models.BooleanField(default=True, help_text="Would you recommend this freelancer?")
    tags = models.CharField(max_length=255, blank=True, default='', help_text="Comma-separated quick tags")

    # Freelancer public reply
    freelancer_reply = models.TextField(blank=True, default='', help_text="Freelancer's one public reply")
    replied_at = models.DateTimeField(null=True, blank=True)

    # Moderation flag
    is_hidden = models.BooleanField(default=False, help_text="Hidden by admin moderation; excluded from aggregates")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.reviewee.username} ({self.overall_rating}/5.0)"

    @property
    def client(self):
        return self.reviewer

    @client.setter
    def client(self, value):
        self.reviewer = value

    @property
    def freelancer(self):
        return self.reviewee

    @freelancer.setter
    def freelancer(self, value):
        self.reviewee = value

    @property
    def is_editable(self):
        """Client can edit the review within 7 days of submission."""
        if not self.created_at:
            return True
        return (timezone.now() - self.created_at).total_seconds() <= 7 * 86400

    @property
    def tags_list(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def save(self, *args, **kwargs):
        # Calculate overall_rating as average of the 4 category ratings rounded to 1 decimal
        q = self.quality_of_work or 5
        c = self.communication or 5
        d = self.deadline_adherence or 5
        p = self.professionalism or 5
        avg = (q + c + d + p) / 4.0
        self.overall_rating = Decimal(str(round(avg, 1)))
        self.rating = int(round(self.overall_rating))
        super().save(*args, **kwargs)


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user.username}: {self.title}"


class ContactMessage(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('closed', 'Closed'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=200)
    topic = models.CharField(max_length=100, blank=True, default='')
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ticket_number} - {self.subject} from {self.name}"

    @property
    def ticket_number(self):
        return f"GB-{self.id:06d}"


class ContactReply(models.Model):
    message = models.ForeignKey(ContactMessage, on_delete=models.CASCADE, related_name='replies')
    replied_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='contact_replies')
    subject = models.CharField(max_length=255)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    email_sent = models.BooleanField(default=True)
    error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"Reply to {self.message.ticket_number} ({self.subject})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_otps')
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"OTP for {self.email} ({self.otp})"

    def is_valid(self):
        """Valid for 10 minutes from creation and not yet used."""
        if self.is_used:
            return False
        return timezone.now() <= self.created_at + timedelta(minutes=10)

    @classmethod
    def generate_otp(cls, user, email):
        import secrets
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        code = f"{secrets.randbelow(900000) + 100000}"
        return cls.objects.create(user=user, email=email, otp=code)



from django.db.models.signals import pre_delete
from django.dispatch import receiver


@receiver(pre_delete, sender=Proposal)
def handle_proposal_pre_delete(sender, instance, **kwargs):
    """
    Cascade clean-up when a Proposal is deleted:
    1. If the proposal has an associated contract, delete it (which cleans payments & milestones).
    2. Reset project status back to 'open' if no other active contract exists.
    3. Restore other proposals that were auto-rejected on acceptance back to 'pending'.
    """
    try:
        project = instance.project
        freelancer = instance.freelancer
        if project:
            # Clean up conversation for this project and freelancer
            Conversation.objects.filter(project=project, participants=freelancer).delete()

            contracts = Contract.objects.filter(
                models.Q(proposal=instance) | models.Q(project=project, freelancer=freelancer)
            )
            for contract in contracts:
                contract.delete()

            remaining_contracts = Contract.objects.filter(project=project).exclude(proposal=instance).exists()
            if not remaining_contracts and project.status == 'in_progress':
                project.status = 'open'
                project.save(update_fields=['status'])
                Proposal.objects.filter(project=project, status='rejected').exclude(pk=instance.pk).update(status='pending')
    except Exception:
        pass


@receiver(pre_delete, sender=Contract)
def handle_contract_pre_delete(sender, instance, **kwargs):
    """
    Cascade clean-up when a Contract is deleted:
    1. Remove all linked payments, milestones, and reviews.
    2. Reset project status to 'open' if no other contracts exist.
    3. Restore rejected proposals back to 'pending'.
    4. Reset the proposal status back to 'pending' if it still exists.
    """
    try:
        Payment.objects.filter(contract=instance).delete()
        Milestone.objects.filter(contract=instance).delete()
        Review.objects.filter(contract=instance).delete()

        project = instance.project
        if project:
            remaining_contracts = Contract.objects.filter(project=project).exclude(pk=instance.pk).exists()
            if not remaining_contracts and project.status == 'in_progress':
                project.status = 'open'
                project.save(update_fields=['status'])
                Proposal.objects.filter(project=project, status='rejected').update(status='pending')

        if instance.proposal and instance.proposal.status == 'accepted':
            instance.proposal.status = 'pending'
            instance.proposal.save(update_fields=['status'])
    except Exception:
        pass


from django.db.models.signals import post_save, post_delete

@receiver(post_save, sender=Proposal)
def create_conversation_on_proposal_accepted(sender, instance, **kwargs):
    """
    Automatically create a Conversation when a proposal is accepted.
    Rule: Accepted-only messaging between client and freelancer.
    """
    if instance.status == 'accepted':
        try:
            Conversation.get_or_create_conversation(
                client=instance.project.client,
                freelancer=instance.freelancer,
                project=instance.project,
                proposal=instance
            )
        except Exception:
            pass


@receiver(post_save, sender=Review)
def handle_review_post_save(sender, instance, created, **kwargs):
    """
    Update freelancer profile aggregates and send in-app/email notification on review save.
    """
    profile = getattr(instance.reviewee, 'profile', None)
    if profile:
        profile.recalculate_stats()

    if created:
        client_name = instance.reviewer.get_full_name() or instance.reviewer.username
        title = f"New {instance.overall_rating}★ Review from {client_name}"
        msg = f"{client_name} left a {instance.overall_rating}/5.0 star review for completed project '{instance.project.title}'."
        try:
            Notification.objects.create(
                user=instance.reviewee,
                title=title,
                message=msg,
                link='/freelancer/reviews/'
            )
        except Exception:
            pass

        try:
            if instance.reviewee.email:
                from django.core.mail import send_mail
                subject = f"[GigBridge] New {instance.overall_rating}★ Review from {client_name}"
                body = (
                    f"Hello {instance.reviewee.username},\n\n"
                    f"{client_name} has submitted a review for project '{instance.project.title}'.\n\n"
                    f"Overall Rating: {instance.overall_rating} / 5.0\n"
                    f"Feedback: \"{instance.comment}\"\n\n"
                    f"You can view your reviews and post your public response at:\n"
                    f"http://127.0.0.1:8000/freelancer/reviews/\n\n"
                    f"Best regards,\nThe GigBridge Team"
                )
                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    [instance.reviewee.email],
                    fail_silently=True
                )
        except Exception:
            pass


@receiver(post_delete, sender=Review)
def handle_review_post_delete(sender, instance, **kwargs):
    """
    Recalculate freelancer profile aggregates when a review is deleted.
    """
    profile = getattr(instance.reviewee, 'profile', None)
    if profile:
        profile.recalculate_stats()