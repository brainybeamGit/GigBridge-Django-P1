from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('client', 'Client / Employer'),
        ('freelancer', 'Freelancer'),
        ('admin', 'Administrator'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    @property
    def average_rating(self):
        reviews = self.user.received_reviews.all()
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return 0.0

    @property
    def skills_list(self):
        return [s.strip() for s in self.skills.split(',') if s.strip()]


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
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Contract: {self.project.title}"

    @property
    def paid_amount(self):
        paid = self.payments.filter(status='completed').aggregate(models.Sum('amount'))['amount__sum']
        return paid or 0.00

    @property
    def remaining_amount(self):
        paid = float(self.paid_amount)
        total = float(self.total_amount)
        return max(0.00, round(total - paid, 2))

    @property
    def advance_milestone(self):
        return self.milestones.filter(milestone_type='advance').first() or self.milestones.order_by('created_at').first()

    @property
    def final_milestone(self):
        return self.milestones.filter(milestone_type='final').first() or self.milestones.order_by('-created_at').first()

    @property
    def is_advance_paid(self):
        adv = self.advance_milestone
        return bool(adv and adv.status == 'paid')

    @property
    def can_start_work(self):
        adv = self.advance_milestone
        return bool(not adv or adv.status == 'paid')

    @property
    def progress_percentage(self):
        if self.status == 'completed':
            return 100
        milestones = self.milestones.all()
        if not milestones.exists():
            return 0
        approved_or_paid = milestones.filter(status__in=['approved', 'paid']).count()
        return int((approved_or_paid / milestones.count()) * 100)


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
        ordering = ['created_at']

    def __str__(self):
        return f"{self.title} ({self.contract.project.title})"


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

    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_reviews')
    reviewee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_reviews')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='reviews')
    contract = models.OneToOneField(Contract, on_delete=models.CASCADE, related_name='review')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by {self.reviewer.username} ({self.rating}/5)"


class ContactMessage(models.Model):
    STATUS_CHOICES = [
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('closed', 'Closed'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField()
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


from django.db.models.signals import post_save

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
