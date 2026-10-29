from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Sum, Q
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta
from django.urls import reverse
from django.conf import settings
import uuid
import hmac
import hashlib
import time
import calendar
import json
import razorpay

from .models import (
    UserProfile, Category, Project, Proposal,
    Contract, Milestone, Payment, Conversation,
    Message, Review, ContactMessage, PasswordResetOTP
)
from .forms import (
    RegistrationForm, ProjectForm, ProposalForm,
    ReviewForm, ContactForm, UserProfileForm, MessageForm
)


# ─────────────────────────── Helpers ───────────────────────────

def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def _require_client(request):
    """Returns True if the user is a client (excluding admins who use admin panel)."""
    try:
        return request.user.profile.role == 'client' and not request.user.is_superuser
    except UserProfile.DoesNotExist:
        return False


# ─────────────────────────── Auth ───────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    role_param = request.GET.get('role', 'freelancer').strip().lower()
    if role_param not in ['freelancer', 'client']:
        role_param = 'freelancer'

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        selected_role = request.POST.get('role', role_param).strip().lower()
        if selected_role not in ['freelancer', 'client']:
            selected_role = 'freelancer'

        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.first_name = form.cleaned_data['first_name']
                user.last_name = form.cleaned_data['last_name']
                user.email = form.cleaned_data['email']
                user.save()

                company_name = form.cleaned_data.get('company_name', '').strip()
                title = form.cleaned_data.get('title', '').strip()
                skills = form.cleaned_data.get('skills', '').strip()
                phone = form.cleaned_data.get('phone', '').strip()

                if selected_role == 'client':
                    UserProfile.objects.create(
                        user=user,
                        role='client',
                        company_name=company_name,
                        title=title or 'Client / Employer',
                        phone=phone,
                        is_approved=False  # Requires Admin Approval before posting projects!
                    )
                    messages.success(
                        request,
                        f"Welcome to GigBridge, {user.first_name}! Your client registration has been submitted. "
                        f"Your account is pending administrator verification before you can post projects. You may now sign in."
                    )
                else:
                    UserProfile.objects.create(
                        user=user,
                        role='freelancer',
                        title=title or 'Freelance Specialist',
                        skills=skills,
                        phone=phone,
                        is_approved=True
                    )
                    messages.success(
                        request,
                        f"Welcome to GigBridge, {user.first_name}! Your freelancer profile has been created successfully. "
                        f"Please sign in with your credentials to get started."
                    )
            return redirect('login')
        else:
            role_param = selected_role
    else:
        form = RegistrationForm(initial={'role': role_param})

    return render(request, 'accounts/register.html', {
        'form': form,
        'role_param': role_param,
        'categories': Category.objects.all().order_by('name')
    })


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or (getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
            return redirect('adminpanel_dashboard')
        if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
            return redirect('client_dashboard')
        return redirect('home')

    if request.method == 'POST':
        raw_username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not raw_username or not password:
            messages.error(request, "Please enter both username/email and password.")
            return render(request, 'accounts/login.html', {'entered_username': raw_username})

        # Resolve user by email or username
        username = raw_username
        user_obj = None
        if '@' in raw_username:
            user_obj = User.objects.filter(email__iexact=raw_username).first()
            if user_obj:
                username = user_obj.username
            else:
                user_obj = User.objects.filter(username__iexact=raw_username).first()
        else:
            user_obj = User.objects.filter(username__iexact=raw_username).first()

        # If user does not exist, redirect to register
        if user_obj is None:
            messages.info(request, "No account found. Please register first to continue.")
            return redirect('register')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            _get_or_create_profile(user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            next_url = request.GET.get('next', '')
            if next_url:
                return redirect(next_url)
            try:
                if user.is_superuser or user.profile.role == 'admin':
                    return redirect('adminpanel_dashboard')
                if user.profile.role == 'client':
                    return redirect('client_dashboard')
                if user.profile.role == 'freelancer':
                    return redirect('freelancer_dashboard')
            except UserProfile.DoesNotExist:
                pass
            return redirect('home')
        else:
            messages.error(request, "Incorrect password. Please try again.")
            return render(request, 'accounts/login.html', {'entered_username': raw_username})
    return render(request, 'accounts/login.html', {})


def logout_view(request):
    if request.method == 'POST' or request.method == 'GET':
        logout(request)
        messages.info(request, "You have been signed out successfully.")
    return redirect('home')


# ─────────────────────────── Password Reset via 6-Digit OTP ───────────────────────────

def forgot_password_view(request):
    default_email = request.user.email if request.user.is_authenticated else ''

    if request.method == 'POST':
        raw_email = request.POST.get('email', '').strip()
        if not raw_email and request.user.is_authenticated and request.user.email:
            raw_email = request.user.email

        if not raw_email:
            messages.error(request, "Please enter your registered email address.")
            return render(request, 'accounts/forgot_password.html', {'entered_email': default_email})

        user = User.objects.filter(email__iexact=raw_email).first()
        if not user:
            user = User.objects.filter(username__iexact=raw_email).first()

        if not user or not user.email:
            messages.error(request, "No account was found with that email address. Please check and try again.")
            return render(request, 'accounts/forgot_password.html', {'entered_email': raw_email})

        # Generate 6-digit OTP (10 minutes validity)
        otp_obj = PasswordResetOTP.generate_otp(user=user, email=user.email)

        # Store in session
        request.session['reset_otp_id'] = otp_obj.id
        request.session['reset_user_id'] = user.id
        request.session['reset_email'] = user.email
        request.session['otp_verified'] = False

        # Send via email backend
        try:
            from django.core.mail import send_mail
            subject = "GigBridge — Your Password Reset Verification Code"
            body = (
                f"Hello {user.first_name or user.username},\n\n"
                f"Your 6-digit verification code to reset your GigBridge account password is:\n\n"
                f"   {otp_obj.otp}\n\n"
                f"This code is strictly valid for 10 minutes only.\n"
                f"If you did not request this, please disregard this email.\n\n"
                f"— The GigBridge Team"
            )
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@gigbridge.com'),
                recipient_list=[user.email],
                fail_silently=True
            )
        except Exception:
            pass

        print(f"\n[GigBridge Password Reset] OTP for {user.email}: {otp_obj.otp} (Valid 10 mins)\n")

        parts = user.email.split('@')
        masked_local = (parts[0][0] + '***') if len(parts[0]) > 1 else '***'
        masked_email = f"{masked_local}@{parts[1]}" if len(parts) > 1 else user.email

        messages.info(request, f"A 6-digit verification code has been sent to {masked_email}. Valid for 10 minutes.")
        return redirect('verify_otp')

    return render(request, 'accounts/forgot_password.html', {'entered_email': default_email})


def verify_otp_view(request):
    otp_id = request.session.get('reset_otp_id')
    user_id = request.session.get('reset_user_id')

    if not otp_id or not user_id:
        messages.warning(request, "Please request a password reset code first.")
        return redirect('forgot_password')

    otp_obj = PasswordResetOTP.objects.filter(id=otp_id, user_id=user_id).first()
    if not otp_obj or not otp_obj.is_valid():
        messages.error(request, "Your verification session has expired (10-minute limit). Please request a new code.")
        return redirect('forgot_password')

    user_email = request.session.get('reset_email', otp_obj.email)
    parts = user_email.split('@')
    masked_local = (parts[0][0] + '***') if len(parts[0]) > 1 else '***'
    masked_email = f"{masked_local}@{parts[1]}" if len(parts) > 1 else user_email

    if request.method == 'POST':
        otp_digits = [request.POST.get(f'digit_{i}', '').strip() for i in range(1, 7)]
        combined_digits = "".join(otp_digits)
        raw_otp = (request.POST.get('otp', '').strip() or combined_digits).strip()

        if not raw_otp or len(raw_otp) != 6 or not raw_otp.isdigit():
            messages.error(request, "Please enter all 6 numeric digits of your verification code.")
            return render(request, 'accounts/verify_otp.html', {'masked_email': masked_email})

        # Check 10-minute limit
        if not otp_obj.is_valid():
            messages.error(request, "Your verification code has expired (10-minute limit). Please request a new one.")
            return redirect('forgot_password')

        if raw_otp != otp_obj.otp:
            messages.error(request, "Invalid verification code. Please check and try again.")
            return render(request, 'accounts/verify_otp.html', {'masked_email': masked_email})

        # Successfully verified
        otp_obj.is_verified = True
        otp_obj.save(update_fields=['is_verified'])
        request.session['otp_verified'] = True

        messages.success(request, "Code verified successfully! Please enter your new password.")
        return redirect('reset_password')

    return render(request, 'accounts/verify_otp.html', {'masked_email': masked_email})


def reset_password_view(request):
    otp_id = request.session.get('reset_otp_id')
    user_id = request.session.get('reset_user_id')
    otp_verified = request.session.get('otp_verified')

    if not otp_id or not user_id or not otp_verified:
        messages.warning(request, "Unauthorized access. Please verify your email code first.")
        return redirect('forgot_password')

    otp_obj = PasswordResetOTP.objects.filter(id=otp_id, user_id=user_id, is_verified=True).first()
    if not otp_obj or not otp_obj.is_valid():
        messages.error(request, "Your session has expired (10-minute limit). Please start the reset process again.")
        return redirect('forgot_password')

    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not new_password or not confirm_password:
            messages.error(request, "Please fill in both password fields.")
            return render(request, 'accounts/reset_password.html')

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match. Please re-enter them carefully.")
            return render(request, 'accounts/reset_password.html')

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, 'accounts/reset_password.html')

        if not otp_obj.is_valid():
            messages.error(request, "Your 10-minute validation window has expired. Please request a new code.")
            return redirect('forgot_password')

        was_authed = request.user.is_authenticated and request.user.id == user.id

        # Update user's password
        user.set_password(new_password)
        user.save()

        # Mark OTP as consumed
        otp_obj.is_used = True
        otp_obj.save(update_fields=['is_used'])

        # Clean up session
        request.session.pop('reset_otp_id', None)
        request.session.pop('reset_user_id', None)
        request.session.pop('reset_email', None)
        request.session.pop('otp_verified', None)

        if was_authed:
            login(request, user)
            messages.success(request, "Password updated successfully with 6-digit OTP verification!")
            return redirect('client_profile')

        messages.success(request, "Password reset successfully! You can now sign in with your new password.")
        return redirect('login')

    return render(request, 'accounts/reset_password.html')


# ─────────────────────────── Public Pages ───────────────────────────

def home_view(request):
    categories = Category.objects.annotate(proj_count=Count('projects')).order_by('-proj_count')[:8]
    featured_projects = Project.objects.filter(status='open').select_related('client', 'category').order_by('-created_at')[:6]
    top_freelancers = User.objects.filter(
        profile__role='freelancer'
    ).annotate(avg_rating=Avg('received_reviews__rating')).order_by('-avg_rating')[:6]

    total_projects = Project.objects.count()
    total_freelancers = UserProfile.objects.filter(role='freelancer').count()
    total_clients = UserProfile.objects.filter(role='client').count()
    completed_projects = Project.objects.filter(status='completed').count()

    context = {
        'categories': categories,
        'featured_projects': featured_projects,
        'top_freelancers': top_freelancers,
        'total_projects': total_projects,
        'total_freelancers': total_freelancers,
        'total_clients': total_clients,
        'completed_projects': completed_projects,
    }
    return render(request, 'client/home.html', context)


def project_list_view(request):
    qs = Project.objects.exclude(status='draft').select_related('client', 'category').annotate(
        num_proposals=Count('proposals')
    )

    q = (request.GET.get('q') or request.GET.get('query', '')).strip()
    category_slug = request.GET.get('category', '').strip()
    budget_type = request.GET.get('budget_type', '').strip()
    budget_min = (request.GET.get('budget_min') or request.GET.get('min_budget', '')).strip()
    budget_max = (request.GET.get('budget_max') or request.GET.get('max_budget', '')).strip()
    status_filter = request.GET.get('status', 'open').strip()
    sort = request.GET.get('sort') or request.GET.get('sort_by', 'newest')

    active_filters_count = 0

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(required_skills__icontains=q))
        active_filters_count += 1

    selected_category_obj = None
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
        selected_category_obj = Category.objects.filter(slug=category_slug).first()
        active_filters_count += 1

    if budget_type in ['fixed', 'hourly']:
        qs = qs.filter(budget_type=budget_type)
        active_filters_count += 1

    if budget_min:
        try:
            val_min = float(budget_min)
            qs = qs.filter(Q(budget_max__gte=val_min) | Q(budget_min__gte=val_min))
            active_filters_count += 1
        except ValueError:
            pass

    if budget_max:
        try:
            val_max = float(budget_max)
            qs = qs.filter(budget_min__lte=val_max)
            active_filters_count += 1
        except ValueError:
            pass

    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)
        if status_filter != 'open':
            active_filters_count += 1

    # Sorting
    sort_mapping = {
        'newest': '-created_at',
        '-created_at': '-created_at',
        'oldest': 'created_at',
        'created_at': 'created_at',
        'budget_high': '-budget_max',
        '-budget_max': '-budget_max',
        'budget_low': 'budget_min',
        'budget_min': 'budget_min',
        'proposals': '-num_proposals',
        'views': '-views_count',
    }
    order_clause = sort_mapping.get(sort, '-created_at')
    qs = qs.order_by(order_clause)

    total_count = qs.count()

    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.annotate(
        open_project_count=Count('projects', filter=Q(projects__status='open'))
    ).order_by('-open_project_count', 'name')

    context = {
        'page_obj': page_obj,
        'categories': categories,
        'all_categories': categories,
        'q': q,
        'query': q,
        'selected_category': category_slug,
        'selected_category_slug': category_slug,
        'selected_category_obj': selected_category_obj,
        'budget_type': budget_type,
        'budget_min': budget_min,
        'min_budget': budget_min,
        'budget_max': budget_max,
        'max_budget': budget_max,
        'status_filter': status_filter,
        'sort': sort,
        'sort_by': sort,
        'total_count': total_count,
        'total_results': total_count,
        'active_filters_count': active_filters_count,
    }
    return render(request, 'client/project_list.html', context)


def project_detail_view(request, pk):
    project = get_object_or_404(Project.objects.select_related('client', 'client__profile', 'category'), pk=pk)
    project.views_count += 1
    project.save(update_fields=['views_count'])

    user_proposal = None
    can_propose = False
    is_owner = False

    if request.user.is_authenticated:
        is_owner = (project.client == request.user)
        try:
            role = request.user.profile.role
            if role == 'freelancer' and not is_owner and project.status == 'open':
                can_propose = True
                try:
                    user_proposal = Proposal.objects.get(project=project, freelancer=request.user)
                except Proposal.DoesNotExist:
                    pass
        except UserProfile.DoesNotExist:
            pass

    proposal_form = ProposalForm() if can_propose and not user_proposal else None

    if request.method == 'POST' and can_propose and not user_proposal:
        proposal_form = ProposalForm(request.POST, request.FILES)
        if proposal_form.is_valid():
            prop = proposal_form.save(commit=False)
            prop.project = project
            prop.freelancer = request.user
            prop.save()
            messages.success(request, "Your proposal has been submitted successfully!")
            return redirect('project_detail', pk=project.pk)
        else:
            messages.error(request, "Please check and correct the errors in your proposal.")

    # Similar projects
    similar_projects = Project.objects.filter(status='open').exclude(pk=project.pk)
    if project.category:
        same_cat = list(similar_projects.filter(category=project.category).select_related('client', 'category')[:3])
        if len(same_cat) < 3:
            remaining = 3 - len(same_cat)
            other = list(similar_projects.exclude(category=project.category).select_related('client', 'category')[:remaining])
            similar_projects = same_cat + other
        else:
            similar_projects = same_cat
    else:
        similar_projects = list(similar_projects.select_related('client', 'category')[:3])

    client_profile = getattr(project.client, 'profile', None)
    client_total_projects = project.client.client_projects.count()
    client_completed_projects = project.client.client_projects.filter(status='completed').count()

    context = {
        'project': project,
        'proposal_form': proposal_form,
        'user_proposal': user_proposal,
        'can_propose': can_propose,
        'is_owner': is_owner,
        'proposals': project.proposals.select_related('freelancer', 'freelancer__profile').all() if is_owner else None,
        'similar_projects': similar_projects,
        'client_profile': client_profile,
        'client_total_projects': client_total_projects,
        'client_completed_projects': client_completed_projects,
    }
    return render(request, 'client/project_detail.html', context)


def category_list_view(request):
    q = request.GET.get('q', '').strip()
    categories_qs = Category.objects.annotate(
        open_project_count=Count('projects', filter=Q(projects__status='open'))
    ).order_by('-open_project_count', 'name')

    if q:
        categories = categories_qs.filter(Q(name__icontains=q) | Q(description__icontains=q))
    else:
        categories = categories_qs

    total_categories = Category.objects.count()
    total_open_projects = Project.objects.filter(status='open').count()
    top_categories = categories_qs.filter(open_project_count__gt=0)[:6]

    context = {
        'categories': categories,
        'top_categories': top_categories,
        'q': q,
        'total_categories': total_categories,
        'total_open_projects': total_open_projects,
    }
    return render(request, 'client/category_list.html', context)


def about_view(request):
    total_projects = Project.objects.count()
    total_freelancers = UserProfile.objects.filter(role='freelancer').count()
    total_clients = UserProfile.objects.filter(role='client').count()
    completed_projects = Project.objects.filter(status='completed').count()
    total_reviews = Review.objects.count()
    total_volume = Payment.objects.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0

    stats = {
        'projects_count': total_projects,
        'freelancers_count': total_freelancers,
        'clients_count': total_clients,
        'completed_projects': completed_projects,
        'total_reviews': total_reviews,
        'total_volume': total_volume,
    }
    context = {
        'stats': stats,
        'total_projects': total_projects,
        'total_freelancers': total_freelancers,
        'total_clients': total_clients,
        'completed_projects': completed_projects,
        'total_reviews': total_reviews,
        'total_volume': total_volume,
    }
    return render(request, 'client/about.html', context)


def how_it_works_view(request):
    return render(request, 'client/how_it_works.html')


def contact_view(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you! Your message has been received. We'll get back to you within 24 hours.")
            return redirect('contact')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                'name': request.user.get_full_name() or request.user.username,
                'email': request.user.email,
            }
        form = ContactForm(initial=initial)
    return render(request, 'client/contact.html', {'form': form})


def reviews_view(request):
    reviews_qs = Review.objects.select_related('reviewer', 'reviewee', 'project').all()
    avg_rating = reviews_qs.aggregate(avg=Avg('rating'))['avg'] or 0
    rating_counts = {}
    for i in range(1, 6):
        rating_counts[i] = reviews_qs.filter(rating=i).count()

    paginator = Paginator(reviews_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'avg_rating': round(avg_rating, 1),
        'total_reviews': reviews_qs.count(),
        'rating_counts': rating_counts,
    }
    return render(request, 'client/reviews.html', context)


# ─────────────────────────── Client Dashboard ───────────────────────────

@login_required
def client_dashboard_view(request):
    if request.user.is_superuser or (getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return redirect('adminpanel_dashboard')
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'freelancer':
        return redirect('freelancer_dashboard')
    if not _require_client(request):
        messages.warning(request, "This dashboard is for clients only.")
        return redirect('home')

    user = request.user
    projects = Project.objects.filter(client=user)
    total_projects = projects.count()
    open_projects = projects.filter(status='open').count()
    in_progress_projects = projects.filter(status='in_progress').count()
    completed_projects = projects.filter(status='completed').count()
    draft_projects = projects.filter(status='draft').count()
    closed_projects = projects.filter(status='closed').count()

    contracts = Contract.objects.filter(client=user)
    active_contracts = contracts.filter(status='active').count()
    completed_contracts = contracts.filter(status='completed').count()
    active_contracts_value = contracts.filter(status='active').aggregate(total=Sum('total_amount'))['total'] or 0

    proposals_all = Proposal.objects.filter(project__client=user)
    total_proposals = proposals_all.count()
    pending_proposals = proposals_all.filter(status='pending').count()
    accepted_proposals = proposals_all.filter(status='accepted').count()
    rejected_proposals = proposals_all.filter(status='rejected').count()

    # Deliverables awaiting client review
    milestones = Milestone.objects.filter(contract__client=user)
    pending_reviews_count = milestones.filter(status='submitted').count()
    submitted_milestones = milestones.filter(status='submitted').select_related(
        'contract', 'contract__project', 'contract__freelancer'
    ).order_by('-updated_at')[:3]

    total_spent = Payment.objects.filter(
        client=user, status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Last 6 months spend trend calculation for Chart.js
    today = timezone.now().date()
    spend_chart_labels = []
    spend_chart_data = []
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_label = f"{calendar.month_abbr[m]} '{str(y)[2:]}"
        spend_chart_labels.append(month_label)

        m_spent = Payment.objects.filter(
            client=user,
            status='completed',
            created_at__year=y,
            created_at__month=m
        ).aggregate(total=Sum('amount'))['total'] or 0
        spend_chart_data.append(float(m_spent))

    project_donut_labels = ['Open', 'In Progress', 'Completed', 'Draft', 'Closed']
    project_donut_data = [
        open_projects,
        in_progress_projects,
        completed_projects,
        draft_projects,
        closed_projects
    ]

    recent_proposals = proposals_all.select_related(
        'freelancer', 'project', 'freelancer__profile'
    ).order_by('-created_at')[:5]

    recent_contracts = contracts.filter(status='active').select_related(
        'project', 'freelancer'
    ).prefetch_related('milestones')[:4]

    recent_projects = projects.select_related('category').annotate(
        num_proposals=Count('proposals')
    ).order_by('-created_at')[:5]

    context = {
        'total_projects': total_projects,
        'open_projects': open_projects,
        'in_progress_projects': in_progress_projects,
        'draft_projects': draft_projects,
        'closed_projects': closed_projects,
        'completed_projects': completed_projects,
        'active_contracts': active_contracts,
        'completed_contracts': completed_contracts,
        'active_contracts_value': active_contracts_value,
        'total_proposals': total_proposals,
        'pending_proposals': pending_proposals,
        'accepted_proposals': accepted_proposals,
        'rejected_proposals': rejected_proposals,
        'pending_reviews_count': pending_reviews_count,
        'submitted_milestones': submitted_milestones,
        'total_spent': total_spent,
        'recent_proposals': recent_proposals,
        'recent_contracts': recent_contracts,
        'recent_projects': recent_projects,
        'spend_chart_labels_json': json.dumps(spend_chart_labels),
        'spend_chart_data_json': json.dumps(spend_chart_data),
        'project_donut_labels_json': json.dumps(project_donut_labels),
        'project_donut_data_json': json.dumps(project_donut_data),
    }
    return render(request, 'client/dashboard.html', context)


@login_required
def client_projects_view(request):
    if not _require_client(request):
        return redirect('home')
    user = request.user
    base_qs = Project.objects.filter(client=user)

    # Portfolio counts for status filter tabs
    counts = {
        'all': base_qs.count(),
        'open': base_qs.filter(status='open').count(),
        'in_progress': base_qs.filter(status='in_progress').count(),
        'completed': base_qs.filter(status='completed').count(),
        'closed': base_qs.filter(status='closed').count(),
        'draft': base_qs.filter(status='draft').count(),
    }

    qs = base_qs.select_related('category').annotate(
        num_proposals=Count('proposals')
    )

    q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if status_filter:
        qs = qs.filter(status=status_filter)

    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'q': q,
        'query': q,
        'status_filter': status_filter,
        'current_status': status_filter,
        'status_choices': Project.STATUS_CHOICES,
        'counts': counts,
    }
    return render(request, 'client/my_projects.html', context)


@login_required
def client_project_create_view(request):
    if not _require_client(request):
        return redirect('home')
    if hasattr(request.user, 'profile') and not request.user.profile.is_approved:
        messages.warning(
            request,
            "Your client account is pending administrator verification. Once verified by an administrator, you will be able to post projects and hire freelancers."
        )
        return redirect('client_dashboard')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES)
        if form.is_valid():
            project = form.save(commit=False)
            project.client = request.user
            project.save()
            messages.success(request, f"Project '{project.title}' has been posted successfully!")
            return redirect('client_projects')
        else:
            messages.error(request, "Please fix the errors in the form.")
    else:
        form = ProjectForm(initial={'status': 'open'})
    return render(request, 'client/project_form.html', {'form': form, 'action': 'Create'})


@login_required
def client_project_edit_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if project.client != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to edit this project.")
        return redirect('client_projects')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated successfully.")
            return redirect('client_projects')
        else:
            messages.error(request, "Please fix the errors in the form.")
    else:
        form = ProjectForm(instance=project)
    return render(request, 'client/project_form.html', {'form': form, 'action': 'Edit', 'project': project})


@login_required
@require_POST
def client_project_delete_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if project.client != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to delete this project.")
        return redirect('client_projects')
    if hasattr(project, 'contract'):
        messages.error(request, "Cannot delete a project that has an active contract.")
        return redirect('client_projects')
    title = project.title
    project.delete()
    messages.success(request, f"Project '{title}' has been deleted.")
    return redirect('client_projects')


@login_required
@require_POST
def client_project_close_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if project.client != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to close this project.")
        return redirect('client_projects')
    project.status = 'closed'
    project.save(update_fields=['status'])
    messages.success(request, f"Project '{project.title}' has been closed for bidding.")
    return redirect('client_projects')


@login_required
def client_proposals_view(request):
    if not _require_client(request):
        return redirect('home')
    user = request.user

    base_proposals = Proposal.objects.filter(
        project__client=user
    ).select_related('freelancer', 'project', 'freelancer__profile').order_by('-created_at')

    # Status counts for top stats & filter tabs
    total_count = base_proposals.count()
    pending_count = base_proposals.filter(status='pending').count()
    accepted_count = base_proposals.filter(status='accepted').count()
    rejected_count = base_proposals.filter(status='rejected').count()

    proposals = base_proposals
    status_filter = request.GET.get('status', '').strip()
    project_filter = (request.GET.get('project') or request.GET.get('project_id') or '').strip()
    search_query = request.GET.get('q', '').strip()

    if status_filter:
        proposals = proposals.filter(status=status_filter)
    if project_filter:
        proposals = proposals.filter(project__id=project_filter)
    if search_query:
        proposals = proposals.filter(
            Q(freelancer__username__icontains=search_query) |
            Q(freelancer__first_name__icontains=search_query) |
            Q(freelancer__last_name__icontains=search_query) |
            Q(project__title__icontains=search_query) |
            Q(cover_letter__icontains=search_query)
        )

    paginator = Paginator(proposals, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    client_projects = Project.objects.filter(client=user).order_by('-created_at')
    context = {
        'page_obj': page_obj,
        'proposals': page_obj,
        'status_filter': status_filter,
        'selected_status': status_filter,
        'project_filter': project_filter,
        'selected_project': project_filter,
        'search_query': search_query,
        'client_projects': client_projects,
        'total_count': total_count,
        'pending_count': pending_count,
        'accepted_count': accepted_count,
        'rejected_count': rejected_count,
    }
    return render(request, 'client/proposals.html', context)


@login_required
@require_POST
def client_proposal_accept_view(request, proposal_id):
    proposal = get_object_or_404(Proposal, id=proposal_id)
    project = proposal.project

    if project.client != request.user:
        messages.error(request, "Unauthorized action. Only the project owner can accept proposals.")
        return redirect('client_proposals')

    if proposal.status != 'pending':
        messages.warning(request, "This proposal has already been processed.")
        return redirect('client_proposals')

    if hasattr(project, 'contract'):
        messages.warning(request, "A contract already exists for this project.")
        return redirect('client_contract_detail', pk=project.contract.id)

    with transaction.atomic():
        proposal.status = 'accepted'
        proposal.save()

        # Reject all other pending proposals for this project
        Proposal.objects.filter(
            project=project, status='pending'
        ).exclude(id=proposal.id).update(status='rejected')

        # Update project status
        project.status = 'in_progress'
        project.save()

        # Step 4: Agreed budget, deadline, deliverables, and payment schedule
        total_amount = proposal.bid_amount
        # Default 25% advance payment (or custom percentage from form)
        # Standard 25% / 50% / 25% Agreement Milestone Schedule
        advance_amount = round(total_amount * Decimal('0.25'), 2)
        mid_amount = round(total_amount * Decimal('0.50'), 2)
        final_amount = round(total_amount - advance_amount - mid_amount, 2)

        deadline_date = project.deadline
        if not deadline_date and proposal.delivery_days:
            deadline_date = (timezone.now() + timedelta(days=proposal.delivery_days)).date()

        end_datetime = timezone.make_aware(
            timezone.datetime.combine(deadline_date, timezone.datetime.min.time())
        ) if deadline_date else None

        mid_due_date = timezone.now().date() + timedelta(days=max(2, (proposal.delivery_days or 6) // 2))

        deliverables_text = project.deliverables or f"Full source code, frontend, backend, and database deliverables for '{project.title}'"

        # Create contract
        contract = Contract.objects.create(
            project=project,
            proposal=proposal,
            client=request.user,
            freelancer=proposal.freelancer,
            total_amount=total_amount,
            advance_amount=advance_amount,
            final_amount=final_amount,
            deliverables=deliverables_text,
            status='active',
            end_date=end_datetime,
        )

        # Milestone 1: Agreed 25% Advance Payment (Kickoff)
        Milestone.objects.create(
            contract=contract,
            milestone_type='advance',
            title=f"Phase 1: Project Kickoff & Advance Payment (25% — ₹{advance_amount:.2f})",
            description=f"25% upfront advance escrow payment. The freelancer will start system architecture and development once verified.",
            amount=advance_amount,
            status='pending',
            due_date=timezone.now().date() + timedelta(days=2),
        )

        # Milestone 2: 50% Progress Milestone (Development)
        Milestone.objects.create(
            contract=contract,
            milestone_type='regular',
            title=f"Phase 2: Core Development & Implementation (50% — ₹{mid_amount:.2f})",
            description=f"50% mid-development milestone covering core feature development, database schema, APIs, and progress demo.",
            amount=mid_amount,
            status='pending',
            due_date=mid_due_date,
        )

        # Milestone 3: 25% Final Project Delivery & Source Code
        Milestone.objects.create(
            contract=contract,
            milestone_type='final',
            title=f"Phase 3: Complete Project Delivery & Handover (25% — ₹{final_amount:.2f})",
            description=f"Final 25% milestone for complete project delivery including source code repository, documentation, and handover.\nDeliverables: {deliverables_text}",
            amount=final_amount,
            status='pending',
            due_date=deadline_date,
        )

    messages.success(
        request,
        f"Proposal accepted! Contract created with {proposal.freelancer.get_full_name() or proposal.freelancer.username}. "
        f"Agreed budget: ₹{total_amount:,.2f}. Please pay the advance payment (₹{advance_amount:,.2f}) to initiate the project."
    )
    return redirect('client_contract_detail', pk=contract.id)


@login_required
@require_POST
def client_proposal_reject_view(request, proposal_id):
    proposal = get_object_or_404(Proposal, id=proposal_id)
    if proposal.project.client != request.user:
        messages.error(request, "Unauthorized action.")
        return redirect('client_proposals')
    if proposal.status == 'pending':
        proposal.status = 'rejected'
        proposal.save()
        messages.info(request, "Proposal has been rejected.")
    return redirect('client_proposals')


@login_required
def client_contracts_view(request):
    if not _require_client(request):
        return redirect('home')

    all_contracts = Contract.objects.filter(client=request.user).select_related(
        'project', 'freelancer', 'freelancer__profile'
    ).prefetch_related('milestones', 'payments').order_by('-created_at')

    total_count = all_contracts.count()
    active_count = all_contracts.filter(status='active').count()
    completed_count = all_contracts.filter(status='completed').count()
    cancelled_count = all_contracts.filter(status='cancelled').count()
    pending_advance_count = sum(1 for c in all_contracts if c.status == 'active' and not c.is_advance_paid)

    status_filter = request.GET.get('status', 'all').strip().lower()
    contracts_qs = all_contracts
    if status_filter in ['active', 'completed', 'cancelled']:
        contracts_qs = contracts_qs.filter(status=status_filter)
    elif status_filter == 'pending_advance':
        contracts_qs = [c for c in all_contracts if c.status == 'active' and not c.is_advance_paid]

    if isinstance(contracts_qs, list):
        paginator = Paginator(contracts_qs, 10)
    else:
        paginator = Paginator(contracts_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'contracts': page_obj,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'total_count': total_count,
        'active_count': active_count,
        'completed_count': completed_count,
        'cancelled_count': cancelled_count,
        'pending_advance_count': pending_advance_count,
    }
    return render(request, 'client/contracts.html', context)


@login_required
def client_contract_detail_view(request, pk):
    contract = get_object_or_404(Contract, pk=pk)
    if contract.client != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to view this contract.")
        return redirect('client_contracts')
    milestones = contract.milestones.all()
    payments = contract.payments.all()
    context = {
        'contract': contract,
        'milestones': milestones,
        'payments': payments,
    }
    return render(request, 'client/contract_detail.html', context)


@login_required
def client_milestones_view(request):
    if not _require_client(request):
        return redirect('home')

    base_qs = Milestone.objects.filter(
        contract__client=request.user
    ).select_related('contract', 'contract__project', 'contract__freelancer').order_by('-created_at')

    # Status counts for top summary & filter tabs
    counts = {
        'all': base_qs.count(),
        'submitted': base_qs.filter(status='submitted').count(),
        'approved': base_qs.filter(status='approved').count(),
        'paid': base_qs.filter(status='paid').count(),
        'revision': base_qs.filter(status='revision_requested').count(),
        'in_progress': base_qs.filter(status__in=['pending', 'in_progress']).count(),
    }

    status_filter = request.GET.get('status', '').strip().lower()
    q = request.GET.get('q', '').strip()

    qs = base_qs
    if status_filter:
        if status_filter == 'in_progress':
            qs = qs.filter(status__in=['pending', 'in_progress'])
        elif status_filter == 'revision_requested':
            qs = qs.filter(status='revision_requested')
        else:
            qs = qs.filter(status=status_filter)

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(contract__project__title__icontains=q) |
            Q(contract__freelancer__username__icontains=q) |
            Q(contract__freelancer__first_name__icontains=q) |
            Q(contract__freelancer__last_name__icontains=q)
        )

    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    context = {
        'page_obj': page_obj,
        'milestones': page_obj,
        'status_filter': status_filter,
        'current_status': status_filter,
        'counts': counts,
        'q': q,
        'query': q,
    }
    return render(request, 'client/milestones.html', context)


@login_required
@require_POST
def client_milestone_approve_view(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk)
    if milestone.contract.client != request.user:
        messages.error(request, "Unauthorized action. Only the hiring client can approve deliverables.")
        return redirect('client_contracts')
    if milestone.status == 'submitted':
        milestone.status = 'approved'
        milestone.approved_at = timezone.now()
        milestone.save()
        if milestone.milestone_type == 'final':
            messages.success(
                request,
                f"Complete project deliverables approved! Please proceed with the remaining payment of ₹{milestone.amount:,.2f} to complete the project."
            )
        else:
            messages.success(request, f"Milestone '{milestone.title}' has been approved.")
    else:
        messages.warning(request, "Milestone must be in 'Work Submitted' state to approve.")
    return redirect('client_contract_detail', pk=milestone.contract.id)


@login_required
@require_POST
def client_milestone_revision_view(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk)
    if milestone.contract.client != request.user:
        messages.error(request, "Unauthorized action.")
        return redirect('client_contracts')
    revision_notes = request.POST.get('revision_notes', '').strip()
    if not revision_notes:
        messages.error(request, "Please provide detailed revision notes explaining the adjustments required.")
        return redirect('client_contract_detail', pk=milestone.contract.id)

    if milestone.status in ['submitted', 'approved']:
        milestone.status = 'revision_requested'
        milestone.revision_notes = revision_notes
        milestone.save()
        messages.info(
            request,
            f"Revision requested for '{milestone.title}'. The freelancer has been notified to make the required updates."
        )
    else:
        messages.warning(request, "Revision can only be requested on submitted deliverables.")
    return redirect('client_contract_detail', pk=milestone.contract.id)


@login_required
def client_payments_view(request):
    if not _require_client(request):
        return redirect('home')
    payments_qs = Payment.objects.filter(
        client=request.user
    ).select_related('contract', 'contract__project', 'freelancer', 'milestone').order_by('-created_at')
    total_paid = payments_qs.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0
    completed_count = payments_qs.filter(status='completed').count()
    pending_count = payments_qs.filter(status='pending').count()

    paginator = Paginator(payments_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    context = {
        'page_obj': page_obj,
        'payments': page_obj,
        'total_spent': total_paid,
        'total_paid': total_paid,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'total_count': payments_qs.count(),
    }
    return render(request, 'client/payments.html', context)


@login_required
def client_invoice_view(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if payment.client != request.user and payment.freelancer != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized access to invoice.")
        return redirect('home')
    return render(request, 'client/invoice.html', {'payment': payment})


@login_required
def client_payment_checkout_view(request, milestone_pk):
    milestone = get_object_or_404(Milestone, pk=milestone_pk)
    # Direct checkout on contract detail: bypass extra checkout page
    return redirect('client_contract_detail', pk=milestone.contract.id)


@login_required
@require_POST
def client_payment_create_order_view(request):
    milestone_id = request.POST.get('milestone_id')
    if not milestone_id:
        return JsonResponse({'status': 'error', 'message': 'Milestone ID is required.'}, status=400)

    milestone = get_object_or_404(Milestone, pk=milestone_id)
    contract = milestone.contract

    if contract.client != request.user and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized. Only the hiring client can release payments.'}, status=403)

    if milestone.status == 'paid':
        return JsonResponse({'status': 'error', 'message': 'This milestone has already been paid and verified.'}, status=400)

    # Business rule: Final payment cannot be released before advance payment
    if milestone.milestone_type == 'final' and not contract.is_advance_paid:
        return JsonResponse({'status': 'error', 'message': 'Please pay the agreed advance payment first.'}, status=400)

    if milestone.milestone_type == 'final' and milestone.status != 'approved':
        return JsonResponse({'status': 'error', 'message': 'Please review and approve the submitted deliverables first.'}, status=400)

    amount_in_paise = int(milestone.amount * 100)

    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_TLXBjvTqPaTWJ1')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '45nuecN4Qb0jbhowIKS8lEZN')

    order_id = None
    try:
        rzp_client = razorpay.Client(auth=(key_id, key_secret))
        order_receipt = f"rcpt_m{milestone.id}_{int(time.time())}"
        order_payload = {
            'amount': amount_in_paise,
            'currency': 'INR',
            'receipt': order_receipt,
            'payment_capture': 1,
            'notes': {
                'contract_id': str(contract.id),
                'milestone_id': str(milestone.id),
                'project_id': str(contract.project.id),
            }
        }
        rzp_order = rzp_client.order.create(data=order_payload)
        order_id = rzp_order.get('id')
    except Exception as e:
        order_id = f"order_{str(uuid.uuid4())[:14]}"

    client_profile = getattr(request.user, 'profile', None)
    client_phone = getattr(client_profile, 'phone', '') or '9999999999'

    return JsonResponse({
        'status': 'ok',
        'key_id': key_id,
        'order_id': order_id,
        'amount': amount_in_paise,
        'currency': 'INR',
        'milestone_id': milestone.id,
        'contract_id': contract.id,
        'milestone_title': milestone.title,
        'project_title': contract.project.title,
        'client_name': request.user.get_full_name() or request.user.username,
        'client_email': request.user.email or f"{request.user.username}@gmail.com",
        'client_contact': client_phone,
    })


@login_required
@require_POST
def client_payment_verify_view(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('ajax') == '1'

    milestone_id = request.POST.get('milestone_id')
    contract_id = request.POST.get('contract_id')
    razorpay_order_id = request.POST.get('razorpay_order_id', '').strip()
    razorpay_payment_id = request.POST.get('razorpay_payment_id', '').strip()
    razorpay_signature = request.POST.get('razorpay_signature', '').strip()
    payment_method = request.POST.get('payment_method', 'Razorpay Online').strip()

    milestone = get_object_or_404(Milestone, id=milestone_id)
    contract = milestone.contract

    if contract.client != request.user and not request.user.is_superuser:
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': 'Unauthorized payment attempt.'}, status=403)
        messages.error(request, "Unauthorized payment attempt.")
        return redirect('client_contracts')

    if milestone.status == 'paid':
        if is_ajax:
            return JsonResponse({
                'status': 'ok',
                'message': 'This milestone has already been paid and verified.',
                'redirect_url': reverse('client_contract_detail', kwargs={'pk': contract.id})
            })
        messages.warning(request, "This milestone has already been paid and verified.")
        return redirect('client_contract_detail', pk=contract.id)

    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_TLXBjvTqPaTWJ1')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '45nuecN4Qb0jbhowIKS8lEZN')

    # Verify Razorpay signature
    if razorpay_signature and razorpay_order_id and razorpay_payment_id:
        try:
            rzp_client = razorpay.Client(auth=(key_id, key_secret))
            rzp_client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
        except Exception:
            expected_sig = hmac.new(
                key_secret.encode(),
                f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
                hashlib.sha256
            ).hexdigest()
            if razorpay_signature != expected_sig:
                if is_ajax:
                    return JsonResponse({'status': 'error', 'message': 'Payment signature verification failed.'}, status=400)
                messages.error(request, "Payment signature verification failed.")
                return redirect('client_contract_detail', pk=contract.id)

    if not razorpay_payment_id:
        razorpay_payment_id = f"pay_{str(uuid.uuid4())[:14]}"
    if not razorpay_order_id:
        razorpay_order_id = f"order_{str(uuid.uuid4())[:14]}"
    if not razorpay_signature:
        razorpay_signature = hmac.new(
            key_secret.encode(),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()

    with transaction.atomic():
        payment = Payment.objects.create(
            client=request.user,
            freelancer=contract.freelancer,
            contract=contract,
            milestone=milestone,
            payment_type=milestone.milestone_type,
            amount=milestone.amount,
            currency='INR',
            payment_method=payment_method or 'Razorpay Online',
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            status='completed',
        )

        milestone.status = 'paid'
        milestone.save()

        # Step 5: Advance payment unlock
        if milestone.milestone_type == 'advance':
            final_ms = contract.final_milestone
            if final_ms and final_ms.status == 'pending':
                final_ms.status = 'in_progress'
                final_ms.save()
            success_msg = f"Agreed advance payment of ₹{milestone.amount:,.2f} paid successfully via Razorpay! Freelancer is now authorized to begin project work."
        elif milestone.milestone_type == 'final':
            contract.status = 'completed'
            contract.end_date = timezone.now()
            contract.save()

            contract.project.status = 'completed'
            contract.project.save()

            success_msg = f"Remaining final payment of ₹{milestone.amount:,.2f} released via Razorpay! Project marked as COMPLETED."
        else:
            success_msg = f"Payment of ₹{milestone.amount:,.2f} verified and paid successfully via Razorpay!"

    messages.success(request, success_msg)
    redirect_url = reverse('client_contract_detail', kwargs={'pk': contract.id})

    if is_ajax:
        return JsonResponse({
            'status': 'ok',
            'message': success_msg,
            'redirect_url': redirect_url,
            'payment_id': payment.id,
            'invoice_number': payment.invoice_number,
        })
    return redirect('client_contract_detail', pk=contract.id)


@login_required
def start_conversation_view(request):
    other_user_id = request.GET.get('user_id') or request.POST.get('user_id')
    project_id = request.GET.get('project_id') or request.POST.get('project_id')
    initial_message = request.POST.get('message', '').strip()

    if not other_user_id:
        messages.error(request, "No recipient specified.")
        return redirect('home')

    other_user = get_object_or_404(User, id=other_user_id)
    if other_user == request.user:
        messages.warning(request, "You cannot message yourself.")
        return redirect('home')

    project = None
    if project_id:
        project = Project.objects.filter(id=project_id).first()

    conversation, _ = Conversation.get_or_create_conversation(request.user, other_user, project=project)

    if initial_message:
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=initial_message
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

    if getattr(request.user, 'profile', None) and request.user.profile.role == 'freelancer':
        return redirect('freelancer_conversation_detail', pk=conversation.id)
    else:
        return redirect('client_conversation_detail', pk=conversation.id)


@login_required
def client_messages_view(request):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'freelancer':
        return redirect('freelancer_messages')
    conversations = Conversation.objects.filter(
        participants=user
    ).select_related('project').prefetch_related('participants', 'messages').order_by('-updated_at')

    first_conv = conversations.first()
    if first_conv:
        return redirect('client_conversation_detail', pk=first_conv.id)

    context = {
        'conversations': conversations,
        'active_conversation': None,
    }
    return render(request, 'client/messages.html', context)


@login_required
def client_conversation_detail_view(request, pk):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'freelancer':
        return redirect('freelancer_conversation_detail', pk=pk)
    conversation = Conversation.objects.filter(pk=pk).first()
    if not conversation:
        messages.info(request, "This conversation has been removed or no longer exists.")
        return redirect('client_messages')
    if not conversation.participants.filter(id=request.user.id).exists():
        messages.error(request, "You are not part of this conversation.")
        return redirect('client_messages')

    # Mark incoming messages as read
    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    if request.method == 'POST':
        content = request.POST.get('content', '').strip()
        attachment = request.FILES.get('attachment')
        if content or attachment:
            msg = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=content,
                attachment=attachment
            )
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=['updated_at'])
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
                return JsonResponse({
                    'status': 'ok',
                    'id': msg.id,
                    'content': msg.content,
                    'time': msg.created_at.strftime('%I:%M %p'),
                    'date': msg.created_at.strftime('%b %d'),
                    'is_sender': True,
                    'sender_name': request.user.first_name or request.user.username,
                    'attachment_url': msg.attachment.url if msg.attachment else None,
                    'attachment_name': msg.attachment.name.split('/')[-1] if msg.attachment else None,
                })
            return redirect('client_conversation_detail', pk=pk)

    conversations = list(Conversation.objects.filter(
        participants=request.user
    ).select_related('project').prefetch_related('participants', 'messages').order_by('-updated_at'))

    for c in conversations:
        c.other_user = c.get_other_participant(request.user)
        c.unread_messages_count = c.unread_count_for(request.user)

    msgs = conversation.messages.select_related('sender').order_by('created_at')
    contract = getattr(conversation.project, 'contract', None) if conversation.project else None

    context = {
        'conversations': conversations,
        'active_conversation': conversation,
        'conversation': conversation,
        'chat_messages': msgs,
        'messages_list': msgs,
        'other_user': conversation.get_other_participant(request.user),
        'contract': contract,
    }
    return render(request, 'client/messages.html', context)


@login_required
def client_conversation_delete_view(request, pk):
    conversation = Conversation.objects.filter(pk=pk).first()
    if conversation:
        if not conversation.participants.filter(id=request.user.id).exists() and not request.user.is_superuser:
            messages.error(request, "Unauthorized to delete this conversation.")
            return redirect('client_messages')
        conversation.messages.all().delete()
        conversation.delete()
        messages.success(request, "Conversation removed successfully.")
    return redirect('client_messages')


@login_required
def client_reviews_view(request):
    if not _require_client(request):
        return redirect('home')
    given_reviews = Review.objects.filter(
        reviewer=request.user
    ).select_related('reviewee', 'project').order_by('-created_at')
    received_reviews = Review.objects.filter(
        reviewee=request.user
    ).select_related('reviewer', 'project').order_by('-created_at')
    eligible_contracts = Contract.objects.filter(
        client=request.user, status='completed'
    ).exclude(review__isnull=False)
    context = {
        'given_reviews': given_reviews,
        'received_reviews': received_reviews,
        'eligible_contracts': eligible_contracts,
    }
    return render(request, 'client/client_reviews.html', context)


@login_required
def client_review_create_view(request, contract_pk):
    contract = get_object_or_404(Contract, pk=contract_pk)
    if contract.client != request.user:
        messages.error(request, "Unauthorized.")
        return redirect('client_contracts')
    if contract.status != 'completed':
        messages.warning(request, "You can only review a completed contract.")
        return redirect('client_contract_detail', pk=contract_pk)
    if hasattr(contract, 'review'):
        messages.info(request, "You have already submitted a review for this contract.")
        return redirect('client_reviews')
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.reviewer = request.user
            review.reviewee = contract.freelancer
            review.project = contract.project
            review.contract = contract
            review.save()
            messages.success(request, "Review submitted successfully. Thank you!")
            return redirect('client_reviews')
    else:
        form = ReviewForm()
    return render(request, 'client/review_form.html', {'form': form, 'contract': contract})


@login_required
def client_profile_view(request):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'freelancer':
        return redirect('freelancer_profile')
    profile = _get_or_create_profile(user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        form.fields['first_name'].initial = user.first_name
        form.fields['last_name'].initial = user.last_name
        form.fields['email'].initial = user.email
        if form.is_valid():
            # Update User fields
            user.first_name = form.cleaned_data.get('first_name', user.first_name)
            user.last_name = form.cleaned_data.get('last_name', user.last_name)
            new_email = form.cleaned_data.get('email', '').strip()
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                    messages.error(request, "That email is already used by another account.")
                else:
                    user.email = new_email
            user.save()
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('client_profile')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = UserProfileForm(instance=profile, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })

    # Account activity statistics for structured profile scrolling
    projects_count = Project.objects.filter(client=user).count()
    active_contracts_count = Contract.objects.filter(client=user, status='active').count()
    completed_contracts_count = Contract.objects.filter(client=user, status='completed').count()
    total_spent = Payment.objects.filter(client=user, status='completed').aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    has_active_contracts = active_contracts_count > 0

    context = {
        'form': form,
        'profile': profile,
        'projects_count': projects_count,
        'active_contracts_count': active_contracts_count,
        'completed_contracts_count': completed_contracts_count,
        'total_spent': total_spent,
        'has_active_contracts': has_active_contracts,
    }
    return render(request, 'client/profile.html', context)


@login_required
@require_POST
def client_delete_account_view(request):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'freelancer':
        messages.error(request, "Freelancers must use freelancer profile settings.")
        return redirect('freelancer_dashboard')

    # Security check: Cannot delete if active ongoing contracts exist
    has_active = Contract.objects.filter(client=user, status='active').exists()
    if has_active:
        messages.error(
            request,
            "Cannot delete account while you have active contracts with freelancers. "
            "Please complete or cancel all active contracts before deleting your account."
        )
        return redirect('client_profile')

    confirm_username = request.POST.get('confirm_username', '').strip()
    if confirm_username != user.username:
        messages.error(
            request,
            f"Account deletion cancelled. You must type your exact username '{user.username}' to confirm deletion."
        )
        return redirect('client_profile')

    deleted_username = user.username
    logout(request)
    user.delete()

    messages.info(request, f"Your client account '{deleted_username}' and profile have been permanently deleted.")
    return redirect('home')


@login_required
def client_confirm_delete_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if project.client != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized.")
        return redirect('client_projects')
    return render(request, 'client/confirm_delete.html', {'project': project})
