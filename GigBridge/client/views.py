from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.cache import patch_vary_headers
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.db.models import Avg, Count, Sum, Q, Exists, OuterRef, Value, BooleanField
from django.core.paginator import Paginator
from django.core.cache import cache
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
    Message, Review, ContactMessage, Submission, PasswordResetOTP, Bookmark
)
from .forms import (
    RegistrationForm, ProjectForm, ProposalForm,
    ReviewForm, ContactForm, UserProfileForm, MessageForm
)
from .helpers import can_message, can_message_conversation
from .currency import (
    get_currency_for_country, get_usd_inr_rate,
    convert_inr_to_usd, convert_usd_to_inr,
    resolve_currency_for_user_or_request
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
                country = form.cleaned_data.get('country', '').strip().upper() or 'IN'
                phone_country_code = form.cleaned_data.get('phone_country_code', '').strip() or '+91'
                phone_number = form.cleaned_data.get('phone_number', '').strip()
                display_currency = get_currency_for_country(country)

                if selected_role == 'client':
                    UserProfile.objects.create(
                        user=user,
                        role='client',
                        company_name=company_name,
                        title=title or 'Client / Employer',
                        phone=phone,
                        country=country,
                        phone_country_code=phone_country_code,
                        phone_number=phone_number,
                        display_currency=display_currency,
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
                        country=country,
                        phone_country_code=phone_country_code,
                        phone_number=phone_number,
                        display_currency=display_currency,
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
    categories = Category.objects.annotate(
        proj_count=Count('projects', filter=Q(projects__status='open'))
    ).order_by('-proj_count')[:8]

    featured_projects = Project.objects.filter(
        status='open'
    ).select_related('client', 'category', 'client__profile').order_by('-created_at')[:6]

    top_freelancers = list(User.objects.filter(
        profile__role='freelancer'
    ).annotate(
        avg_rating=Avg('received_reviews__overall_rating', filter=Q(received_reviews__is_hidden=False)),
        review_count=Count('received_reviews', filter=Q(received_reviews__is_hidden=False))
    ).select_related('profile').order_by('-avg_rating', '-review_count')[:4])

    for f in top_freelancers:
        profile = getattr(f, 'profile', None)
        if profile and profile.skills:
            f.skills_list = [s.strip() for s in profile.skills.split(',') if s.strip()][:3]
        else:
            f.skills_list = []

    # Real counts from database (no fake hardcoded numbers)
    completed_contracts_count = Contract.objects.filter(status='completed').count()
    freelancers_count = UserProfile.objects.filter(role='freelancer').count()
    open_projects_count = Project.objects.filter(status='open').count()

    total_projects = Project.objects.count()
    total_freelancers = freelancers_count
    total_clients = UserProfile.objects.filter(role='client').count()
    completed_projects = completed_contracts_count or Project.objects.filter(status='completed').count()

    # Testimonials: latest 3 visible 4-star or 5-star reviews; if fewer than 3 exist, hide section completely
    testimonials_qs = list(Review.objects.filter(
        is_hidden=False,
        overall_rating__gte=4.0
    ).select_related('reviewer', 'reviewee', 'project').order_by('-created_at')[:3])
    testimonials = testimonials_qs if len(testimonials_qs) >= 3 else []

    context = {
        'categories': categories,
        'featured_projects': featured_projects,
        'top_freelancers': top_freelancers,
        'total_projects': total_projects,
        'total_freelancers': total_freelancers,
        'total_clients': total_clients,
        'completed_projects': completed_projects,
        'completed_contracts_count': completed_contracts_count,
        'freelancers_count': freelancers_count,
        'open_projects_count': open_projects_count,
        'testimonials': testimonials,
    }
    return render(request, 'client/home.html', context)


def project_list_view(request):
    """
    Browse Projects job board with search, categories, budget range, status,
    sort, pagination, and real-time bookmark annotations.
    """
    qs = Project.objects.exclude(status='draft').select_related(
        'client', 'client__profile', 'category'
    ).annotate(
        proposals_count=Count('proposals', distinct=True)
    )

    # Annotate is_bookmarked in a single query
    if request.user.is_authenticated:
        user_bookmarks = Bookmark.objects.filter(project=OuterRef('pk'), user=request.user)
        qs = qs.annotate(is_bookmarked=Exists(user_bookmarks))
    else:
        qs = qs.annotate(is_bookmarked=Value(False, output_field=BooleanField()))

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

    curr = resolve_currency_for_user_or_request(request=request)

    if budget_min:
        try:
            val_min = Decimal(str(budget_min))
            if curr == 'USD':
                val_min = convert_usd_to_inr(val_min)
            qs = qs.filter(Q(budget_max__gte=val_min) | Q(budget_min__gte=val_min))
            active_filters_count += 1
        except Exception:
            pass

    if budget_max:
        try:
            val_max = Decimal(str(budget_max))
            if curr == 'USD':
                val_max = convert_usd_to_inr(val_max)
            qs = qs.filter(budget_min__lte=val_max)
            active_filters_count += 1
        except Exception:
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
        'proposals': '-proposals_count',
        'proposals_many': '-proposals_count',
        'proposals_few': 'proposals_count',
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

    open_projects_count = Project.objects.filter(status='open').count()
    user_bookmarks_count = Bookmark.objects.filter(user=request.user).count() if request.user.is_authenticated else 0

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
        'open_projects_count': open_projects_count,
        'user_bookmarks_count': user_bookmarks_count,
    }
    return render(request, 'client/project_list.html', context)


@require_POST
def project_bookmark_toggle_view(request, pk):
    """
    AJAX endpoint to toggle bookmark state on a project for authenticated users.
    Returns JSON { status: 'ok', bookmarked: bool, count: int }.
    """
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'unauthenticated',
            'login_url': reverse('login') + f'?next={request.META.get("HTTP_REFERER", reverse("project_list"))}'
        }, status=401)

    project = get_object_or_404(Project, pk=pk)
    bookmark, created = Bookmark.objects.get_or_create(user=request.user, project=project)
    if not created:
        bookmark.delete()
        bookmarked = False
    else:
        bookmarked = True

    count = project.bookmarks.count()
    return JsonResponse({
        'status': 'ok',
        'bookmarked': bookmarked,
        'count': count,
        'project_id': project.id,
    })


@login_required
def saved_projects_view(request):
    """
    Displays all projects saved/bookmarked by the logged-in user.
    """
    qs = Project.objects.filter(
        bookmarks__user=request.user
    ).select_related('client', 'client__profile', 'category').annotate(
        proposals_count=Count('proposals', distinct=True),
        is_bookmarked=Value(True, output_field=BooleanField())
    ).order_by('-bookmarks__created_at')

    q = (request.GET.get('q') or request.GET.get('query', '')).strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(required_skills__icontains=q))

    total_count = qs.count()
    paginator = Paginator(qs, 8)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'total_results': total_count,
        'total_count': total_count,
        'q': q,
        'is_saved_view': True,
    }
    return render(request, 'client/saved_projects.html', context)


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

    proposal_form = ProposalForm(user=request.user) if can_propose and not user_proposal else None

    if request.method == 'POST' and can_propose and not user_proposal:
        proposal_form = ProposalForm(request.POST, request.FILES, user=request.user)
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
    sent_ticket = request.GET.get('sent', '').strip()
    if request.method == 'POST':
        # Honeypot check: reject bots silently
        if request.POST.get('website_url'):
            return redirect('contact')

        form = ContactForm(request.POST)
        if form.is_valid():
            contact_msg = form.save(commit=False)
            contact_msg.status = 'new'
            # Extract client IP address if available
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                contact_msg.ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                contact_msg.ip_address = request.META.get('REMOTE_ADDR')
            contact_msg.save()
            ticket_no = contact_msg.ticket_number
            messages.success(request, f"Message sent! We'll reply to your email within 4 hours. (Ticket #{ticket_no})")
            return redirect(f"{reverse('contact')}?sent={ticket_no}")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                'name': request.user.get_full_name() or request.user.username,
                'email': request.user.email,
            }
            profile = getattr(request.user, 'profile', None)
            if profile:
                if getattr(profile, 'country', None):
                    initial['country'] = profile.country
                if getattr(profile, 'phone_number', None):
                    initial['phone'] = profile.phone_number
        form = ContactForm(initial=initial)
    return render(request, 'client/contact.html', {
        'form': form,
        'sent_ticket': sent_ticket,
    })


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
        form = ProjectForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.client = request.user
            project.save()
            messages.success(request, f"Project '{project.title}' has been posted successfully!")
            return redirect('client_projects')
        else:
            messages.error(request, "Please fix the errors in the form.")
    else:
        form = ProjectForm(initial={'status': 'open'}, user=request.user)
    return render(request, 'client/project_form.html', {'form': form, 'action': 'Create'})


@login_required
def client_project_edit_view(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if project.client != request.user and not request.user.is_superuser:
        messages.error(request, "You are not authorized to edit this project.")
        return redirect('client_projects')
    if request.method == 'POST':
        form = ProjectForm(request.POST, request.FILES, instance=project, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated successfully.")
            return redirect('client_projects')
        else:
            messages.error(request, "Please fix the errors in the form.")
    else:
        form = ProjectForm(instance=project, user=request.user)
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

        today = timezone.now().date()
        delivery_days = proposal.delivery_days or 14

        # Calculate strict increasing due dates: due_date_1 < due_date_2 < due_date_3
        due_date_1 = today + timedelta(days=2)
        mid_days = max(4, delivery_days // 2)
        due_date_2 = today + timedelta(days=mid_days)
        if due_date_2 <= due_date_1:
            due_date_2 = due_date_1 + timedelta(days=3)

        due_date_3 = today + timedelta(days=max(delivery_days, mid_days + 4))
        if project.deadline and project.deadline > due_date_2:
            due_date_3 = project.deadline
        elif due_date_3 <= due_date_2:
            due_date_3 = due_date_2 + timedelta(days=5)

        end_datetime = timezone.make_aware(
            timezone.datetime.combine(due_date_3, timezone.datetime.min.time())
        )

        deliverables_text = project.deliverables or f"Full source code, frontend, backend, and database deliverables for '{project.title}'"

        # Create contract with locked exchange rate and base currency
        current_rate = get_usd_inr_rate()
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
            contract_currency='INR',
            exchange_rate_used=current_rate,
        )

        # Milestone 1: Agreed 25% Advance Payment (Kickoff) - order=1, active (in_progress)
        Milestone.objects.create(
            contract=contract,
            order=1,
            milestone_type='advance',
            title=f"Phase 1: Project Kickoff & Advance Payment (25% — ₹{advance_amount:.2f})",
            description=f"25% upfront advance escrow payment. The freelancer will start system architecture and development once verified.",
            amount=advance_amount,
            status='in_progress',
            due_date=due_date_1,
        )

        # Milestone 2: 50% Progress Milestone (Development) - order=2, pending (locked)
        Milestone.objects.create(
            contract=contract,
            order=2,
            milestone_type='regular',
            title=f"Phase 2: Core Development & Implementation (50% — ₹{mid_amount:.2f})",
            description=f"50% mid-development milestone covering core feature development, database schema, APIs, and progress demo.",
            amount=mid_amount,
            status='pending',
            due_date=due_date_2,
        )

        # Milestone 3: 25% Final Project Delivery & Source Code - order=3, pending (locked)
        Milestone.objects.create(
            contract=contract,
            order=3,
            milestone_type='final',
            title=f"Phase 3: Complete Project Delivery & Handover (25% — ₹{final_amount:.2f})",
            description=f"Final 25% milestone for complete project delivery including source code repository, documentation, and handover.\nDeliverables: {deliverables_text}",
            amount=final_amount,
            status='pending',
            due_date=due_date_3,
        )

        # Create or link Conversation immediately for accepted proposal
        Conversation.get_or_create_conversation(
            client=request.user,
            freelancer=proposal.freelancer,
            project=project,
            proposal=proposal
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
        return HttpResponseForbidden("You are not authorized to view this contract.")
    milestones = contract.milestones.all().order_by('order', 'id')
    payments = contract.payments.filter(status='completed').order_by('-created_at')
    active_ms = contract.get_active_milestone()
    context = {
        'contract': contract,
        'milestones': milestones,
        'payments': payments,
        'active_ms': active_ms,
        'advance_ms': contract.advance_milestone,
        'final_ms': contract.final_milestone,
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
def client_milestone_approve_view(request, pk=None, contract_id=None, milestone_id=None):
    mid = milestone_id or pk
    milestone = get_object_or_404(Milestone, pk=mid)
    contract = milestone.contract

    if contract.client != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized action. Only the hiring client can approve deliverables.")
        return HttpResponseForbidden("Unauthorized action. Only the hiring client can approve deliverables.")

    if contract_id and contract.id != contract_id:
        messages.error(request, "Milestone does not belong to the specified contract.")
        return redirect('client_contract_detail', pk=contract.id)

    if not milestone.can_approve(request.user):
        messages.warning(
            request,
            f"Cannot approve Phase {milestone.order} ('{milestone.title}'): deliverables can only be approved on the active milestone in 'Work Submitted' state."
        )
        return redirect('client_contract_detail', pk=contract.id)

    with transaction.atomic():
        ms_locked = Milestone.objects.select_for_update().get(id=milestone.id)
        if not ms_locked.can_approve(request.user):
            messages.warning(request, "Milestone status changed.")
            return redirect('client_contract_detail', pk=contract.id)

        ms_locked.status = 'approved'
        ms_locked.approved_at = timezone.now()
        ms_locked.save()

    messages.success(
        request,
        f"Deliverables for Phase {ms_locked.order}: '{ms_locked.title}' approved! Please proceed with the escrow release payment of ₹{ms_locked.amount:,.2f}."
    )
    return redirect('client_contract_detail', pk=contract.id)


@login_required
@require_POST
def client_milestone_revision_view(request, pk=None, contract_id=None, milestone_id=None):
    mid = milestone_id or pk
    milestone = get_object_or_404(Milestone, pk=mid)
    contract = milestone.contract

    if contract.client != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized action.")
        return HttpResponseForbidden("Unauthorized action.")

    if contract_id and contract.id != contract_id:
        messages.error(request, "Milestone does not belong to the specified contract.")
        return redirect('client_contract_detail', pk=contract.id)

    revision_notes = request.POST.get('revision_notes', '').strip()
    if not revision_notes:
        messages.error(request, "Please provide detailed revision notes explaining the adjustments required.")
        return redirect('client_contract_detail', pk=milestone.contract.id)

    if not milestone.can_request_revision(request.user):
        messages.warning(request, f"Revision can only be requested on submitted deliverables for the active milestone.")
        return redirect('client_contract_detail', pk=milestone.contract.id)

    with transaction.atomic():
        ms_locked = Milestone.objects.select_for_update().get(id=milestone.id)
        if not ms_locked.can_request_revision(request.user):
            messages.warning(request, "Milestone status changed.")
            return redirect('client_contract_detail', pk=contract.id)

        ms_locked.status = 'revision_requested'
        ms_locked.revision_notes = revision_notes
        ms_locked.save()

    messages.info(
        request,
        f"Revision requested for Phase {ms_locked.order}: '{ms_locked.title}'. The freelancer has been notified to make the required updates."
    )
    return redirect('client_contract_detail', pk=milestone.contract.id)


@login_required
def contract_milestone_submit_view(request, contract_id, milestone_id=None):
    """Unified handler or alias for milestone submission across client/freelancer routes."""
    from freelancer.views import submit_delivery_view as f_submit
    return f_submit(request, contract_id=contract_id, milestone_id=milestone_id)


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

    # Strict server-side enforcement: Check can_pay()
    if not milestone.can_pay(request.user):
        if milestone.is_locked:
            prev = milestone.previous_milestone
            prev_order = prev.order if prev else 1
            return JsonResponse({'status': 'error', 'message': f'Cannot pay Phase {milestone.order}: Phase {prev_order} must be paid first.'}, status=400)
        if not milestone.is_active:
            active = contract.get_active_milestone()
            active_info = f"Phase {active.order}" if active else "None"
            return JsonResponse({'status': 'error', 'message': f'Cannot pay Phase {milestone.order}: {active_info} is currently active and must be processed first.'}, status=400)
        if milestone.status != 'approved' and milestone.milestone_type != 'advance' and milestone.order > 1:
            return JsonResponse({'status': 'error', 'message': f'Please review and approve the submitted deliverables for Phase {milestone.order} first.'}, status=400)
        return JsonResponse({'status': 'error', 'message': 'This milestone is not eligible for payment release at this time.'}, status=400)

    # Calculate charge amount & currency based on settings and client preference
    rate = contract.exchange_rate_used or get_usd_inr_rate()
    client_currency = getattr(getattr(request.user, 'profile', None), 'display_currency', 'INR')
    payment_curr_setting = getattr(settings, 'PAYMENT_CURRENCY', 'INR').upper()

    if client_currency == 'USD' and payment_curr_setting == 'USD':
        charge_currency = 'USD'
        charge_amount = convert_inr_to_usd(milestone.amount, rate=rate)
        amount_in_smallest_unit = int(round(charge_amount * 100))  # cents
        charge_note = f"Charged in USD: ${charge_amount:.2f}"
    else:
        charge_currency = 'INR'
        charge_amount = milestone.amount
        amount_in_smallest_unit = int(round(charge_amount * 100))  # paise
        if client_currency == 'USD':
            usd_equiv = convert_inr_to_usd(milestone.amount, rate=rate)
            charge_note = f"Charged in INR: ₹{charge_amount:,.2f} INR (approx. ${usd_equiv:.2f} USD at locked rate 1 USD = ₹{rate:.2f})."
        else:
            charge_note = f"Amount to pay: ₹{charge_amount:,.2f} INR"

    key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_TLXBjvTqPaTWJ1')
    key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '45nuecN4Qb0jbhowIKS8lEZN')

    order_id = None
    try:
        rzp_client = razorpay.Client(auth=(key_id, key_secret))
        order_receipt = f"rcpt_m{milestone.id}_{int(time.time())}"
        order_payload = {
            'amount': amount_in_smallest_unit,
            'currency': charge_currency,
            'receipt': order_receipt,
            'payment_capture': 1,
            'notes': {
                'contract_id': str(contract.id),
                'milestone_id': str(milestone.id),
                'project_id': str(contract.project.id),
                'client_currency': client_currency,
                'charge_currency': charge_currency,
                'base_amount_inr': str(milestone.amount),
                'exchange_rate': str(rate),
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
        'amount': amount_in_smallest_unit,
        'currency': charge_currency,
        'display_amount': float(charge_amount),
        'charge_note': charge_note,
        'base_amount_inr': float(milestone.amount),
        'exchange_rate': float(rate),
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
        ms_locked = Milestone.objects.select_for_update().get(id=milestone.id)
        contract_locked = Contract.objects.select_for_update().get(id=contract.id)

        # Idempotency check inside lock: prevent paying the same milestone twice
        if ms_locked.status == 'paid' or Payment.objects.filter(milestone=ms_locked, status='completed').exists():
            existing_payment = Payment.objects.filter(milestone=ms_locked, status='completed').first()
            redirect_url = reverse('contract_review_create', kwargs={'contract_id': contract_locked.id}) if contract_locked.all_milestones_paid else reverse('client_contract_detail', kwargs={'pk': contract_locked.id})
            if is_ajax:
                return JsonResponse({
                    'status': 'ok',
                    'message': f"Phase {ms_locked.order}: '{ms_locked.title}' has already been paid and verified.",
                    'redirect_url': redirect_url,
                    'payment_id': existing_payment.id if existing_payment else 0,
                    'invoice_number': existing_payment.invoice_number if existing_payment else '',
                })
            messages.info(request, f"Phase {ms_locked.order}: '{ms_locked.title}' has already been paid.")
            return redirect(redirect_url)

        # Validate that earlier milestones are paid
        if ms_locked.is_locked:
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': f'Cannot pay Phase {ms_locked.order}: previous milestones must be settled first.'}, status=400)
            messages.error(request, "Earlier milestones must be paid first.")
            return redirect('client_contract_detail', pk=contract_locked.id)

        # Determine charge amount & currency based on settings and client currency
        rate = contract_locked.exchange_rate_used or get_usd_inr_rate()
        client_currency = getattr(getattr(request.user, 'profile', None), 'display_currency', 'INR')
        payment_curr_setting = getattr(settings, 'PAYMENT_CURRENCY', 'INR').upper()

        if client_currency == 'USD' and payment_curr_setting == 'USD':
            charge_currency = 'USD'
            charge_amount = convert_inr_to_usd(ms_locked.amount, rate=rate)
        else:
            charge_currency = 'INR'
            charge_amount = ms_locked.amount

        # Create single Payment and Invoice
        payment = Payment.objects.create(
            client=request.user,
            freelancer=contract_locked.freelancer,
            contract=contract_locked,
            milestone=ms_locked,
            payment_type=ms_locked.milestone_type,
            amount=charge_amount,
            currency=charge_currency,
            base_amount_inr=ms_locked.amount,
            exchange_rate=rate,
            payment_method=payment_method or 'Razorpay Online',
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            status='completed',
        )

        ms_locked.status = 'paid'
        ms_locked.save(update_fields=['status'])

        # Activate the NEXT sequential milestone
        next_ms = contract_locked.milestones.filter(order__gt=ms_locked.order).order_by('order').first()
        if next_ms:
            next_ms.status = 'in_progress'
            next_ms.save(update_fields=['status'])
            success_msg = f"Payment of ₹{ms_locked.amount:,.2f} for Phase {ms_locked.order} ('{ms_locked.title}') released via Razorpay! Phase {next_ms.order} ('{next_ms.title}') is now active."
        else:
            success_msg = f"Final payment of ₹{ms_locked.amount:,.2f} for Phase {ms_locked.order} released via Razorpay!"

        # Contract completed ONLY when EVERY milestone is paid
        if contract_locked.all_milestones_paid:
            contract_locked.status = 'completed'
            contract_locked.end_date = timezone.now()
            contract_locked.save(update_fields=['status', 'end_date'])

            contract_locked.project.status = 'completed'
            contract_locked.project.save(update_fields=['status'])
            success_msg += " All contract milestones are paid — project marked as COMPLETED!"
            redirect_url = reverse('contract_review_create', kwargs={'contract_id': contract_locked.id})
        else:
            redirect_url = reverse('client_contract_detail', kwargs={'pk': contract_locked.id})

    messages.success(request, success_msg)
    if is_ajax:
        return JsonResponse({
            'status': 'ok',
            'message': success_msg,
            'redirect_url': redirect_url,
            'payment_id': payment.id,
            'invoice_number': payment.invoice_number,
        })
    return redirect(redirect_url)


# ─────────────────────────── Accepted-Only Messaging & Chat (Part A) ───────────────────────────

@login_required
def messages_inbox_view(request):
    """
    Inbox page: /messages/ (name: messages_inbox)
    Lists all accepted conversations with last message preview, unread count badge,
    and project name, newest first.
    """
    user = request.user
    all_convs = Conversation.objects.filter(
        Q(participants=user) | Q(client=user) | Q(freelancer=user)
    ).select_related('project', 'project__client', 'client', 'freelancer').prefetch_related('messages', 'participants').order_by('-updated_at').distinct()

    valid_convs = []
    for conv in all_convs:
        if can_message_conversation(user, conv):
            conv.other_user = conv.get_other_participant(user)
            conv.unread_count = conv.unread_count_for(user)
            conv.last_msg = conv.messages.order_by('-created_at').first()
            valid_convs.append(conv)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        sq = search_query.lower()
        valid_convs = [
            c for c in valid_convs
            if (c.project and sq in c.project.title.lower()) or
               (c.other_user and (sq in c.other_user.username.lower() or sq in (c.other_user.get_full_name() or '').lower()))
        ]

    context = {
        'conversations': valid_convs,
        'search_query': search_query,
    }
    return render(request, 'client/messages_inbox.html', context)


@login_required
def conversation_detail_view(request, conversation_id):
    """
    Chat UI page: /messages/<conversation_id>/ (name: conversation_detail)
    Server-side security verification: checks request user is client or freelancer
    and proposal is accepted.
    Header with project title & other user avatar.
    Scrollable message list (blue on right for sender, grey on left for recipient).
    Send box with optional file attachment.
    """
    conversation = get_object_or_404(
        Conversation.objects.select_related('project', 'project__client', 'client', 'freelancer'),
        id=conversation_id
    )

    if not can_message_conversation(request.user, conversation):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Messaging is restricted to accepted proposals.'}, status=403)
        messages.error(request, "Messaging access denied. Clients and freelancers can only chat once a proposal is accepted.")
        return redirect('messages_inbox')

    # Record active user presence in cache for online status indicator
    cache.set(f'user_last_seen_{request.user.id}', timezone.now().timestamp(), timeout=45)

    # Automatically mark unread incoming messages as read upon opening
    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    other_user = conversation.get_other_participant(request.user)
    contract = getattr(conversation.project, 'contract', None) if conversation.project else None

    # Check other user online status
    is_other_online = False
    if other_user:
        last_seen = cache.get(f'user_last_seen_{other_user.id}')
        if last_seen and (timezone.now().timestamp() - last_seen) < 30:
            is_other_online = True

    # Role-based quick reply message suggestions
    user_role = getattr(getattr(request.user, 'profile', None), 'role', 'freelancer')
    if user_role == 'freelancer':
        default_quick_messages = [
            "Hi! I'm reviewing the project specifications now and ready to begin.",
            "Working on the deliverables right now, everything is on schedule.",
            "I've uploaded the milestone deliverables for your review.",
            "Could you please clarify this requirement when you have a moment?",
            "All requested revisions have been completed according to feedback.",
        ]
    else:
        default_quick_messages = [
            "Hello! Glad to have you on board. Let's make this project a great success.",
            "Please share a quick progress update when convenient.",
            "The latest deliverable looks great, thank you!",
            "Could you make a minor adjustment or revision on this?",
            "Milestone approved! Ready to proceed with the next phase.",
        ]

    # Handle standard form POST submission if JavaScript is disabled
    if request.method == 'POST':
        body = request.POST.get('body') or request.POST.get('content', '').strip()
        attachment = request.FILES.get('attachment')
        if body or attachment:
            Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=body,
                attachment=attachment
            )
            conversation.updated_at = timezone.now()
            conversation.save(update_fields=['updated_at'])
            return redirect('conversation_detail', conversation_id=conversation.id)

    chat_messages = conversation.messages.select_related('sender', 'sender__profile').order_by('created_at')

    context = {
        'conversation': conversation,
        'other_user': other_user,
        'chat_messages': chat_messages,
        'contract': contract,
        'latest_message_id': chat_messages.last().id if chat_messages.exists() else 0,
        'is_other_online': is_other_online,
        'default_quick_messages': default_quick_messages,
        'user_role': user_role,
    }
    return render(request, 'client/conversation_detail.html', context)


@login_required
@require_POST
def send_message_view(request, conversation_id):
    """
    Endpoint: /messages/<conversation_id>/send/ (name: send_message)
    POST-only with CSRF.
    Enforces server-side security. Returns JSON for AJAX fetch or redirects.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)

    if not can_message_conversation(request.user, conversation):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized chat access.'}, status=403)

    # Keep sender active in cache
    cache.set(f'user_last_seen_{request.user.id}', timezone.now().timestamp(), timeout=45)

    body = request.POST.get('body') or request.POST.get('content', '').strip()
    attachment = request.FILES.get('attachment')

    if not body and not attachment:
        return JsonResponse({'status': 'error', 'message': 'Message body or attachment required.'}, status=400)

    msg = Message.objects.create(
        conversation=conversation,
        sender=request.user,
        content=body,
        attachment=attachment
    )
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=['updated_at'])

    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'fetch' in request.META.get('HTTP_ACCEPT', '') or request.GET.get('ajax') == '1'
    if is_ajax:
        return JsonResponse({
            'status': 'ok',
            'id': msg.id,
            'body': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender.first_name or msg.sender.username,
            'is_me': True,
            'is_read': msg.is_read,
            'created_at_time': msg.created_at.strftime('%I:%M %p'),
            'created_at_date': msg.created_at.strftime('%b %d, %Y'),
            'attachment_url': msg.attachment.url if msg.attachment else None,
            'attachment_name': msg.attachment.name.split('/')[-1] if msg.attachment else None,
        })

    return redirect('conversation_detail', conversation_id=conversation.id)


@login_required
def fetch_new_messages_view(request, conversation_id):
    """
    Endpoint: /messages/<conversation_id>/fetch/ (name: fetch_new_messages)
    GET JSON endpoint for auto-refresh polling every 5 seconds.
    Returns messages where id > last_id, updates seen receipts, and returns online status.
    """
    conversation = get_object_or_404(Conversation, id=conversation_id)

    if not can_message_conversation(request.user, conversation):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized chat access.'}, status=403)

    # Keep request user active in cache
    cache.set(f'user_last_seen_{request.user.id}', timezone.now().timestamp(), timeout=45)

    try:
        last_id = int(request.GET.get('last_id', 0))
    except (ValueError, TypeError):
        last_id = 0

    new_messages = conversation.messages.filter(id__gt=last_id).select_related('sender').order_by('created_at')

    # Mark incoming new messages as read
    conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    # All message IDs sent by request.user that are now marked as read
    read_message_ids = list(
        conversation.messages.filter(sender=request.user, is_read=True).values_list('id', flat=True)
    )

    # Check other user online status
    other_user = conversation.get_other_participant(request.user)
    is_other_online = False
    if other_user:
        last_seen = cache.get(f'user_last_seen_{other_user.id}')
        if last_seen and (timezone.now().timestamp() - last_seen) < 30:
            is_other_online = True

    items = []
    for msg in new_messages:
        items.append({
            'id': msg.id,
            'body': msg.content,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender.first_name or msg.sender.username,
            'is_me': (msg.sender_id == request.user.id),
            'is_read': msg.is_read,
            'created_at_time': msg.created_at.strftime('%I:%M %p'),
            'created_at_date': msg.created_at.strftime('%b %d, %Y'),
            'attachment_url': msg.attachment.url if msg.attachment else None,
            'attachment_name': msg.attachment.name.split('/')[-1] if msg.attachment else None,
        })

    return JsonResponse({
        'status': 'ok',
        'messages': items,
        'read_message_ids': read_message_ids,
        'other_user_online': is_other_online,
    })


@login_required
def start_conversation_view(request):
    """
    Initiates or redirects to a conversation.
    Strictly verifies can_message(user, project) before granting access.
    """
    other_user_id = request.GET.get('user_id') or request.POST.get('user_id')
    project_id = request.GET.get('project_id') or request.POST.get('project_id')
    initial_message = request.POST.get('message', '').strip()

    if not other_user_id:
        messages.error(request, "No recipient specified.")
        return redirect('messages_inbox')

    other_user = get_object_or_404(User, id=other_user_id)
    if other_user == request.user:
        messages.warning(request, "You cannot message yourself.")
        return redirect('messages_inbox')

    project = None
    if project_id:
        project = Project.objects.filter(id=project_id).first()

    # Rule: Can only message if proposal is accepted or contract exists
    if project:
        if not can_message(request.user, project, other_user=other_user):
            messages.warning(request, "Messaging is restricted. Clients and freelancers can only chat once a proposal is accepted on this project.")
            return redirect('project_detail', pk=project.id)
    else:
        shares_accepted = Proposal.objects.filter(
            Q(project__client=request.user, freelancer=other_user) |
            Q(project__client=other_user, freelancer=request.user),
            status='accepted'
        ).exists()
        shares_contract = Contract.objects.filter(
            Q(client=request.user, freelancer=other_user) |
            Q(client=other_user, freelancer=request.user)
        ).exists()
        if not (shares_accepted or shares_contract or request.user.is_superuser):
            messages.warning(request, "Direct messaging is available only between clients and freelancers with an accepted proposal.")
            return redirect('messages_inbox')

    if project and project.client_id == request.user.id:
        client_user = request.user
        freelancer_user = other_user
    elif project and project.client_id == other_user.id:
        client_user = other_user
        freelancer_user = request.user
    elif getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        client_user = request.user
        freelancer_user = other_user
    else:
        client_user = other_user
        freelancer_user = request.user

    conversation, _ = Conversation.get_or_create_conversation(
        client=client_user,
        freelancer=freelancer_user,
        project=project
    )

    if initial_message:
        Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=initial_message
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

    return redirect('conversation_detail', conversation_id=conversation.id)


@login_required
def client_messages_view(request):
    return redirect('messages_inbox')


@login_required
def client_conversation_detail_view(request, pk):
    return redirect('conversation_detail', conversation_id=pk)


@login_required
def conversation_delete_view(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if not conversation.participants.filter(id=request.user.id).exists() and not request.user.is_superuser:
        messages.error(request, "Unauthorized to delete this conversation.")
        return redirect('messages_inbox')
    conversation.messages.all().delete()
    conversation.delete()
    messages.success(request, "Conversation removed successfully.")
    return redirect('messages_inbox')


@login_required
def client_conversation_delete_view(request, pk):
    return conversation_delete_view(request, conversation_id=pk)


# ─────────────────────────── Freelancer Public Profile (Part B) ───────────────────────────

@login_required
def freelancer_public_profile_view(request, id):
    """
    Public freelancer profile page viewable by logged-in clients and admins.
    URL: /freelancers/<id>/ (name: freelancer_public_profile)
    Sections:
    - Header: photo, name, title/headline, location, member since, verified badge, skills, hourly rate.
    - Badges automatically awarded from data:
        * 'Top Rated' if rating >= 4.7 and total_reviews >= 5
        * 'Rising Talent' if completed >= 1 and total_reviews < 5
        * 'New on GigBridge' if completed == 0
        * 'On-Time Pro' if on_time_delivery_rate >= 90% and completed >= 1
    - Live calculated Stats: completed projects, in progress, on-time %, would recommend %, repeat clients.
    - Rating Breakdown card: big score, star display, total reviews, 4 category progress bars, 5-to-1 breakdown.
    - Work History with tabs (All / Completed / In Progress).
    - Reviews list with sorting (Newest, Highest, Lowest), reviewer privacy formatting, tags, replies, and pagination.
    - Proposal Context Card (if opened from a proposal): project title, bid, delivery, cover letter.
    - Privacy: Hides email & phone until proposal is accepted.
    """
    freelancer_user = get_object_or_404(
        User.objects.select_related('profile'),
        id=id
    )
    profile = getattr(freelancer_user, 'profile', None)
    if profile:
        profile.recalculate_stats()

    # Optional proposal context if passed from client proposals list
    proposal_id = request.GET.get('proposal_id')
    proposal_context = None
    if proposal_id:
        proposal_context = Proposal.objects.filter(
            id=proposal_id, freelancer=freelancer_user
        ).select_related('project', 'project__category').first()
        if proposal_context and proposal_context.project.client_id != request.user.id and not request.user.is_superuser:
            proposal_context = None

    # Privacy Protection: Email and phone hidden until proposal is accepted or active contract
    can_view_private = False
    if request.user.is_authenticated:
        if request.user.id == freelancer_user.id or request.user.is_superuser:
            can_view_private = True
        else:
            has_accepted_proposal = Proposal.objects.filter(
                project__client=request.user,
                freelancer=freelancer_user,
                status='accepted'
            ).exists()
            has_contract = Contract.objects.filter(
                client=request.user,
                freelancer=freelancer_user
            ).exists()
            can_view_private = has_accepted_proposal or has_contract

    # Check for existing conversation or chat access
    can_message = False
    conversation_id = None
    if request.user.is_authenticated and request.user.id != freelancer_user.id:
        conv = Conversation.objects.filter(
            client=request.user,
            freelancer=freelancer_user
        ).first()
        if not conv:
            conv = Conversation.objects.filter(
                freelancer=request.user,
                client=freelancer_user
            ).first()
        if conv:
            can_message = True
            conversation_id = conv.id
        else:
            has_acc = Proposal.objects.filter(
                project__client=request.user,
                freelancer=freelancer_user,
                status='accepted'
            ).first()
            if has_acc:
                can_message = True

    # Live platform contracts stats
    contracts_base = Contract.objects.filter(freelancer=freelancer_user)
    completed_contracts_count = contracts_base.filter(status='completed').count()
    in_progress_contracts_count = contracts_base.filter(status='active').count()

    total_proposals = Proposal.objects.filter(freelancer=freelancer_user).count()
    accepted_proposals = Proposal.objects.filter(freelancer=freelancer_user, status='accepted').count()
    acceptance_rate = round((accepted_proposals / total_proposals) * 100) if total_proposals > 0 else 0

    # Reviews & Ratings aggregation (only non-hidden reviews)
    review_sort = request.GET.get('review_sort', 'newest').strip()
    reviews_base = Review.objects.filter(reviewee=freelancer_user, is_hidden=False).select_related('reviewer', 'project', 'contract')
    if review_sort == 'highest':
        reviews_base = reviews_base.order_by('-overall_rating', '-created_at')
    elif review_sort == 'lowest':
        reviews_base = reviews_base.order_by('overall_rating', '-created_at')
    else:
        reviews_base = reviews_base.order_by('-created_at')

    total_reviews = reviews_base.count()

    # 5-Star to 1-Star Rating breakdown bars
    rating_breakdown = []
    for star in [5, 4, 3, 2, 1]:
        if star == 5:
            star_count = reviews_base.filter(overall_rating__gte=4.5).count()
        elif star == 1:
            star_count = reviews_base.filter(overall_rating__lt=2.0).count()
        else:
            star_count = reviews_base.filter(overall_rating__gte=star - 0.5, overall_rating__lt=star + 0.5).count()
        star_pct = round((star_count / total_reviews) * 100) if total_reviews > 0 else 0
        rating_breakdown.append({
            'star': star,
            'count': star_count,
            'percent': star_pct,
        })

    # Work History Filter Tabs
    history_tab = request.GET.get('history_tab', 'all').strip()
    history_qs = contracts_base.select_related('project', 'project__category', 'client', 'review').order_by('-created_at')
    if history_tab == 'completed':
        history_qs = history_qs.filter(status='completed')
    elif history_tab == 'in_progress':
        history_qs = history_qs.filter(status='active')

    paginator_history = Paginator(history_qs, 6)
    history_page_num = request.GET.get('history_page', 1)
    history_page_obj = paginator_history.get_page(history_page_num)

    # Reviews Pagination (5 per page)
    paginator_reviews = Paginator(reviews_base, 5)
    reviews_page_num = request.GET.get('reviews_page', 1)
    reviews_page_obj = paginator_reviews.get_page(reviews_page_num)

    context = {
        'freelancer_user': freelancer_user,
        'profile': profile,
        'proposal_context': proposal_context,
        'can_view_private': can_view_private,
        'can_message': can_message,
        'conversation_id': conversation_id,
        'completed_contracts_count': completed_contracts_count,
        'in_progress_contracts_count': in_progress_contracts_count,
        'total_proposals': total_proposals,
        'accepted_proposals': accepted_proposals,
        'acceptance_rate': acceptance_rate,
        'total_reviews': total_reviews,
        'rating_breakdown': rating_breakdown,
        'review_sort': review_sort,
        'history_tab': history_tab,
        'history_page_obj': history_page_obj,
        'reviews_page_obj': reviews_page_obj,
    }
    return render(request, 'client/freelancer_profile.html', context)


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
def contract_review_create_view(request, contract_id=None, contract_pk=None):
    """
    Client rates and reviews a freelancer after contract completion.
    URL: /contracts/<id>/review/ (name: contract_review_create)
    Rule:
    - Contract status must be 'completed'
    - Only hiring client of that contract can submit
    - One review per contract (if already exists, redirects to edit if <= 7 days, else locked)
    """
    cid = contract_id or contract_pk
    contract = get_object_or_404(
        Contract.objects.select_related('project', 'freelancer', 'client', 'freelancer__profile'),
        id=cid
    )

    # Permission check: hiring client only
    if contract.client != request.user and not request.user.is_superuser:
        messages.error(request, "Only the client who hired the freelancer on this contract can submit a review.")
        return redirect('client_contract_detail', pk=contract.id)

    # Status check: contract must be completed
    if contract.status != 'completed':
        messages.warning(request, "You can rate and review the freelancer once all milestones are completed and paid.")
        return redirect('client_contract_detail', pk=contract.id)

    # Check for existing review
    existing_review = getattr(contract, 'review', None)
    if existing_review:
        if existing_review.is_editable:
            messages.info(request, "You have already reviewed this contract. You can edit your review within 7 days.")
            return redirect('contract_review_edit', contract_id=contract.id)
        else:
            messages.warning(request, "This contract has already been reviewed, and the 7-day edit window has expired.")
            return redirect('client_contract_detail', pk=contract.id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.contract = contract
            review.reviewer = request.user
            review.reviewee = contract.freelancer
            review.project = contract.project
            review.save()
            freelancer_name = contract.freelancer.get_full_name() or contract.freelancer.username
            messages.success(request, f"Thank you! Your {review.overall_rating}★ review for {freelancer_name} has been posted.")
            return redirect('client_contract_detail', pk=contract.id)
        else:
            messages.error(request, "Please check the form and fix any highlighted errors.")
    else:
        form = ReviewForm()

    context = {
        'contract': contract,
        'freelancer_user': contract.freelancer,
        'form': form,
        'is_edit': False,
    }
    return render(request, 'client/contract_review.html', context)


@login_required
def contract_review_edit_view(request, contract_id):
    """
    Client edits their submitted review within the 7-day window.
    URL: /contracts/<id>/review/edit/ (name: contract_review_edit)
    """
    contract = get_object_or_404(
        Contract.objects.select_related('project', 'freelancer', 'client', 'review'),
        id=contract_id
    )

    if contract.client != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized access to review.")
        return redirect('client_contract_detail', pk=contract.id)

    existing_review = getattr(contract, 'review', None)
    if not existing_review:
        messages.info(request, "No review found for this contract yet. You can submit one now.")
        return redirect('contract_review_create', contract_id=contract.id)

    if not existing_review.is_editable:
        messages.warning(request, "This review is locked. Reviews can only be edited within 7 days of posting.")
        return redirect('client_contract_detail', pk=contract.id)

    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=existing_review)
        if form.is_valid():
            review = form.save()
            messages.success(request, "Your review has been updated successfully.")
            return redirect('client_contract_detail', pk=contract.id)
        else:
            messages.error(request, "Please fix the highlighted errors.")
    else:
        form = ReviewForm(instance=existing_review)

    context = {
        'contract': contract,
        'freelancer_user': contract.freelancer,
        'form': form,
        'review': existing_review,
        'is_edit': True,
    }
    return render(request, 'client/contract_review.html', context)


def client_review_create_view(request, contract_pk):
    """Alias pointing to contract_review_create_view for backward compatibility."""
    return contract_review_create_view(request, contract_id=contract_pk)
    return render(request, 'client/review_form.html', {'form': form, 'contract': contract})


@login_required
def client_profile_view(request):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'freelancer':
        return redirect('freelancer_profile')
    profile = _get_or_create_profile(user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
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
        form = UserProfileForm(instance=profile, user=request.user, initial={
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


def currency_switch_view(request, code=None):
    """
    Rebuilt currency switcher view:
    - Validates currency code ('INR' or 'USD').
    - Sets cookie 'gb_currency' (1 year, samesite Lax, path '/').
    - If user is logged in, also updates user.profile.display_currency.
    - Validates 'next' parameter with url_has_allowed_host_and_scheme to avoid open redirects.
    - Attaches Vary: Cookie header to prevent full-page cache collisions.
    """
    currency = (code or request.GET.get('currency') or request.POST.get('currency') or '').strip().upper()
    if currency not in ['INR', 'USD']:
        currency = 'INR'

    next_url = request.GET.get('next') or request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    is_safe = url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    )
    if not is_safe:
        next_url = '/'

    response = redirect(next_url)
    response.set_cookie(
        'gb_currency',
        currency,
        max_age=365 * 24 * 3600,
        samesite='Lax',
        path='/'
    )
    patch_vary_headers(response, ('Cookie',))

    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        request.user.profile.display_currency = currency
        request.user.profile.save(update_fields=['display_currency'])

    return response


# Alias for backward compatibility
set_currency_view = currency_switch_view


@login_required
@require_POST
def complete_profile_currency_view(request):
    """
    Modal/banner submission for existing users missing country/phone.
    Validates phone with phonenumbers, sets country, phone, and display_currency.
    """
    country = request.POST.get('country', '').strip().upper() or 'IN'
    phone_raw = request.POST.get('phone', '').strip()
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'

    if not url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
        next_url = '/'

    profile = getattr(request.user, 'profile', None)
    if not profile:
        profile = UserProfile.objects.create(user=request.user)

    if not phone_raw:
        messages.error(request, "Please enter your phone number to complete your profile.")
        return redirect(next_url)

    try:
        import phonenumbers
        parsed = phonenumbers.parse(phone_raw, country)
        if not phonenumbers.is_valid_number(parsed):
            COUNTRY_NAMES = {
                'IN': 'India', 'US': 'United States', 'GB': 'United Kingdom',
                'AE': 'United Arab Emirates', 'CA': 'Canada', 'AU': 'Australia',
                'DE': 'Germany', 'FR': 'France', 'SG': 'Singapore'
            }
            country_name = COUNTRY_NAMES.get(country, country)
            messages.error(request, f"Enter a valid phone number for {country_name}.")
            return redirect(next_url)

        profile.country = phonenumbers.region_code_for_number(parsed) or country
        profile.phone_country_code = f"+{parsed.country_code}"
        profile.phone_number = str(parsed.national_number)
        profile.phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        profile.display_currency = 'INR' if profile.country == 'IN' else 'USD'
        profile.save()

        messages.success(request, f"Profile updated. Your default currency is set to {profile.display_currency}.")
        response = redirect(next_url)
        response.set_cookie('gb_currency', profile.display_currency, max_age=365*24*3600, samesite='Lax', path='/')
        patch_vary_headers(response, ('Cookie',))
        return response
    except Exception:
        messages.error(request, "Invalid phone number format. Please check your country code and digits.")
        return redirect(next_url)
