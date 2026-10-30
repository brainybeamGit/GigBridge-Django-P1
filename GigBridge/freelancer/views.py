import json
import calendar
from decimal import Decimal
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction

from client.models import (
    Project, Proposal, Contract, Milestone, Payment, Review, UserProfile, Category,
    Conversation, Message, Submission
)
from client.forms import UserProfileForm, FreelancerReplyForm


def _require_freelancer(request):
    """Returns True if the user is a freelancer."""
    try:
        return request.user.profile.role == 'freelancer' and not request.user.is_superuser
    except Exception:
        return False


@login_required
def dashboard_view(request):
    if request.user.is_superuser or (getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'):
        return redirect('adminpanel_dashboard')
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_dashboard')

    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Proposals
    proposals = Proposal.objects.filter(freelancer=user)
    total_proposals = proposals.count()
    pending_proposals = proposals.filter(status='pending').count()
    accepted_proposals = proposals.filter(status='accepted').count()
    rejected_proposals = proposals.filter(status='rejected').count()

    # Contracts
    contracts = Contract.objects.filter(freelancer=user)
    active_contracts = contracts.filter(status='active').count()
    completed_contracts = contracts.filter(status='completed').count()

    # Earnings
    total_earnings = Payment.objects.filter(
        freelancer=user, status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Milestones
    milestones = Milestone.objects.filter(contract__freelancer=user)
    completed_milestones = milestones.filter(status__in=['approved', 'paid']).count()
    pending_milestones = milestones.filter(status__in=['pending', 'in_progress', 'revision_requested'])

    # Recent Data
    recent_contracts = contracts.filter(status='active').select_related(
        'project', 'client', 'client__profile'
    ).prefetch_related('milestones').order_by('-created_at')[:4]

    recent_proposals = proposals.select_related(
        'project', 'project__client', 'project__category'
    ).order_by('-created_at')[:5]

    # Reviews & Rating
    reviews = Review.objects.filter(reviewee=user).order_by('-created_at')
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 5.0

    # Active contracts value
    active_contracts_value = contracts.filter(status='active').aggregate(total=Sum('total_amount'))['total'] or 0

    # Win / Conversion rate
    conversion_rate = round((accepted_proposals / total_proposals) * 100, 1) if total_proposals > 0 else 0.0

    # Pending deliverables / revisions
    pending_deliverables = Milestone.objects.filter(
        contract__freelancer=user,
        contract__status='active',
        status__in=['pending', 'in_progress', 'revision_requested']
    ).select_related('contract', 'contract__project', 'contract__client').order_by('due_date')[:4]

    # Last 6 months earnings trend for Chart.js
    today = timezone.now().date()
    earnings_chart_labels = []
    earnings_chart_data = []
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_label = f"{calendar.month_abbr[m]} '{str(y)[2:]}"
        earnings_chart_labels.append(month_label)

        m_earned = Payment.objects.filter(
            freelancer=user,
            status='completed',
            created_at__year=y,
            created_at__month=m
        ).aggregate(total=Sum('amount'))['total'] or 0
        earnings_chart_data.append(float(m_earned))

    proposal_donut_labels = ['Accepted', 'Pending', 'Declined']
    proposal_donut_data = [accepted_proposals, pending_proposals, rejected_proposals]

    context = {
        'profile': profile,
        'total_proposals': total_proposals,
        'pending_proposals': pending_proposals,
        'accepted_proposals': accepted_proposals,
        'rejected_proposals': rejected_proposals,
        'active_contracts': active_contracts,
        'completed_contracts': completed_contracts,
        'active_contracts_value': active_contracts_value,
        'conversion_rate': conversion_rate,
        'total_earnings': total_earnings,
        'completed_milestones': completed_milestones,
        'pending_milestones': pending_milestones[:4],
        'pending_deliverables': pending_deliverables,
        'recent_contracts': recent_contracts,
        'recent_proposals': recent_proposals,
        'avg_rating': round(avg_rating, 1),
        'reviews_count': reviews.count(),
        'earnings_chart_labels_json': json.dumps(earnings_chart_labels),
        'earnings_chart_data_json': json.dumps(earnings_chart_data),
        'proposal_donut_labels_json': json.dumps(proposal_donut_labels),
        'proposal_donut_data_json': json.dumps(proposal_donut_data),
    }
    return render(request, 'freelancer/dashboard.html', context)


@login_required
def profile_view(request):
    user = request.user
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_profile')

    profile, _ = UserProfile.objects.get_or_create(user=user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile, user=user)
        form.fields['first_name'].initial = user.first_name
        form.fields['last_name'].initial = user.last_name
        form.fields['email'].initial = user.email

        if form.is_valid():
            user.first_name = form.cleaned_data.get('first_name', user.first_name)
            user.last_name = form.cleaned_data.get('last_name', user.last_name)
            new_email = form.cleaned_data.get('email', '').strip()
            if new_email and new_email != user.email:
                if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
                    messages.error(request, "That email is already registered to another account.")
                else:
                    user.email = new_email
            user.save()
            form.save()
            messages.success(request, "Your profile has been updated successfully!")
            return redirect('freelancer_profile')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = UserProfileForm(instance=profile, user=user, initial={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
        })

    reviews = Review.objects.filter(reviewee=user)
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 5.0

    # Account activity statistics for structured profile scrolling
    total_contracts = Contract.objects.filter(freelancer=user).count()
    active_contracts_count = Contract.objects.filter(freelancer=user, status='active').count()
    completed_contracts_count = Contract.objects.filter(freelancer=user, status='completed').count()
    proposals_count = Proposal.objects.filter(freelancer=user).count()
    total_earned = Payment.objects.filter(
        contract__freelancer=user, status='completed'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    has_active_contracts = active_contracts_count > 0

    context = {
        'form': form,
        'profile': profile,
        'avg_rating': round(avg_rating, 1),
        'reviews_count': reviews.count(),
        'total_contracts': total_contracts,
        'active_contracts_count': active_contracts_count,
        'completed_contracts_count': completed_contracts_count,
        'proposals_count': proposals_count,
        'total_earned': total_earned,
        'has_active_contracts': has_active_contracts,
    }
    return render(request, 'freelancer/profile.html', context)


@login_required
@require_POST
def freelancer_delete_account_view(request):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'client':
        return redirect('client_profile')

    # Security check: Cannot delete if active ongoing contracts exist
    has_active = Contract.objects.filter(freelancer=user, status='active').exists()
    if has_active:
        messages.error(
            request,
            "Cannot delete account while you have active ongoing contracts with clients. "
            "Please complete or resolve all active contracts before deleting your account."
        )
        return redirect('freelancer_profile')

    confirm_username = request.POST.get('confirm_username', '').strip()
    if confirm_username != user.username:
        messages.error(
            request,
            f"Account deletion cancelled. You must type your exact username '{user.username}' to confirm deletion."
        )
        return redirect('freelancer_profile')

    deleted_username = user.username
    logout(request)
    user.delete()

    messages.info(request, f"Your freelancer account '{deleted_username}' and profile have been permanently deleted.")
    return redirect('home')


@login_required
def proposals_view(request):
    user = request.user
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_proposals')

    status_filter = request.GET.get('status', 'all')
    proposals_qs = Proposal.objects.filter(freelancer=user).select_related(
        'project', 'project__client', 'project__category'
    )

    if status_filter in ['pending', 'accepted', 'rejected', 'withdrawn']:
        proposals_qs = proposals_qs.filter(status=status_filter)

    total_count = Proposal.objects.filter(freelancer=user).count()
    pending_count = Proposal.objects.filter(freelancer=user, status='pending').count()
    accepted_count = Proposal.objects.filter(freelancer=user, status='accepted').count()
    rejected_count = Proposal.objects.filter(freelancer=user, status='rejected').count()

    context = {
        'proposals': proposals_qs.order_by('-created_at'),
        'status_filter': status_filter,
        'total_count': total_count,
        'pending_count': pending_count,
        'accepted_count': accepted_count,
        'rejected_count': rejected_count,
    }
    return render(request, 'freelancer/proposals.html', context)


@login_required
def contracts_view(request):
    user = request.user
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_contracts')

    status_filter = request.GET.get('status', 'all')
    contracts_qs = Contract.objects.filter(freelancer=user).select_related(
        'project', 'client', 'client__profile'
    ).prefetch_related('milestones')

    if status_filter in ['active', 'completed', 'cancelled']:
        contracts_qs = contracts_qs.filter(status=status_filter)

    active_count = Contract.objects.filter(freelancer=user, status='active').count()
    completed_count = Contract.objects.filter(freelancer=user, status='completed').count()
    total_val = Contract.objects.filter(freelancer=user).aggregate(total=Sum('total_amount'))['total'] or 0

    context = {
        'contracts': contracts_qs.order_by('-created_at'),
        'status_filter': status_filter,
        'active_count': active_count,
        'completed_count': completed_count,
        'total_val': total_val,
    }
    return render(request, 'freelancer/contracts.html', context)


@login_required
def messages_view(request):
    return redirect('messages_inbox')


@login_required
def conversation_detail_view(request, pk):
    return redirect('conversation_detail', conversation_id=pk)


@login_required
def conversation_delete_view(request, pk):
    conversation = Conversation.objects.filter(pk=pk).first()
    if conversation:
        if not conversation.participants.filter(id=request.user.id).exists() and not request.user.is_superuser:
            messages.error(request, "Unauthorized to delete this conversation.")
            return redirect('freelancer_messages')
        conversation.messages.all().delete()
        conversation.delete()
        messages.success(request, "Conversation removed successfully.")
    return redirect('freelancer_messages')


@login_required
def contract_detail_view(request, pk):
    user = request.user
    if getattr(user, 'profile', None) and user.profile.role == 'client':
        return redirect('client_contract_detail', pk=pk)

    contract = get_object_or_404(
        Contract.objects.select_related('project', 'client', 'client__profile'),
        pk=pk
    )
    if contract.freelancer != user and not user.is_superuser:
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
    return render(request, 'freelancer/contract_detail.html', context)


@login_required
def submit_delivery_view(request, contract_id, milestone_id=None):
    if request.method != 'POST':
        return redirect('freelancer_contract_detail', pk=contract_id)

    contract = get_object_or_404(Contract, id=contract_id)
    if contract.freelancer != request.user and not request.user.is_superuser:
        messages.error(request, "Unauthorized action. You are not the freelancer assigned to this contract.")
        return HttpResponseForbidden("Unauthorized action. You are not the freelancer assigned to this contract.")

    # The active milestone is the only one that can receive submissions
    active_ms = contract.get_active_milestone()
    if not active_ms:
        messages.error(request, "All milestones for this contract are already completed and paid.")
        return redirect('freelancer_contract_detail', pk=contract.id)

    # Server-side validation: if milestone_id provided, it MUST be the active milestone
    if milestone_id:
        target_ms = get_object_or_404(Milestone, id=milestone_id, contract_id=contract.id)
        if target_ms.id != active_ms.id:
            messages.error(
                request,
                f"Cannot submit deliverables for Phase {target_ms.order} ('{target_ms.title}'). "
                f"Phase {active_ms.order} ('{active_ms.title}') is the active milestone and must be completed first."
            )
            return redirect('freelancer_contract_detail', pk=contract.id)
    else:
        target_ms = active_ms

    if not target_ms.can_submit(request.user):
        messages.error(
            request,
            f"Deliverables cannot be submitted for Phase {target_ms.order} ('{target_ms.title}') while in '{target_ms.get_status_display()}' state."
        )
        return redirect('freelancer_contract_detail', pk=contract.id)

    submission_notes = request.POST.get('submission_notes', '').strip()
    deliverable_link = request.POST.get('deliverable_link', '').strip()
    submission_file = request.FILES.get('submission_file')

    if not submission_notes and not submission_file and not deliverable_link:
        messages.error(request, "Please provide description notes, a repository/demo link, or upload your source code deliverable.")
        return redirect('freelancer_contract_detail', pk=contract.id)

    with transaction.atomic():
        ms_locked = Milestone.objects.select_for_update().get(id=target_ms.id)
        if not ms_locked.can_submit(request.user):
            messages.error(request, "Submission rejected: Milestone status changed.")
            return redirect('freelancer_contract_detail', pk=contract.id)

        # Create submission record
        Submission.objects.create(
            milestone=ms_locked,
            contract=contract,
            freelancer=request.user,
            submission_notes=submission_notes,
            deliverable_link=deliverable_link,
            submission_file=submission_file,
        )

        ms_locked.submission_notes = submission_notes
        if deliverable_link:
            ms_locked.deliverable_link = deliverable_link
        if submission_file:
            ms_locked.submission_file = submission_file
        ms_locked.status = 'submitted'
        ms_locked.submitted_at = timezone.now()
        ms_locked.save()

    messages.success(
        request,
        f"Deliverables for Phase {ms_locked.order}: '{ms_locked.title}' submitted successfully! Awaiting client review."
    )
    return redirect('freelancer_contract_detail', pk=contract.id)


@login_required
def earnings_view(request):
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_dashboard')

    user = request.user
    payments_qs = Payment.objects.filter(freelancer=user).select_related(
        'contract', 'contract__project', 'client', 'milestone'
    ).order_by('-created_at')

    # Total completed earnings
    total_earned = payments_qs.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0

    # Active contracts pending pipeline value
    contracts = Contract.objects.filter(freelancer=user)
    total_contract_value = contracts.aggregate(total=Sum('total_amount'))['total'] or 0
    active_contracts = contracts.filter(status='active')
    active_pipeline_value = active_contracts.aggregate(total=Sum('total_amount'))['total'] or 0

    # In-escrow / pending payment: active contracts value minus what has already been paid on active contracts
    active_paid = payments_qs.filter(contract__in=active_contracts, status='completed').aggregate(total=Sum('amount'))['total'] or 0
    pending_escrow = max(0, active_pipeline_value - active_paid)

    # Completed payouts count
    completed_payouts_count = payments_qs.filter(status='completed').count()

    # Milestone breakdown
    milestones = Milestone.objects.filter(contract__freelancer=user)
    approved_milestones_count = milestones.filter(status__in=['approved', 'paid']).count()

    # Filter status if requested
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'completed':
        filtered_payments = payments_qs.filter(status='completed')
    elif status_filter == 'pending':
        filtered_payments = payments_qs.filter(status='pending')
    else:
        filtered_payments = payments_qs

    paginator = Paginator(filtered_payments, 10)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    # Last 6 months earnings trend for Chart.js
    today = timezone.now().date()
    earnings_chart_labels = []
    earnings_chart_data = []
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        month_label = f"{calendar.month_abbr[m]} '{str(y)[2:]}"
        earnings_chart_labels.append(month_label)

        m_earned = payments_qs.filter(
            status='completed',
            created_at__year=y,
            created_at__month=m
        ).aggregate(total=Sum('amount'))['total'] or 0
        earnings_chart_data.append(float(m_earned))

    context = {
        'payments': page_obj,
        'page_obj': page_obj,
        'total_earned': total_earned,
        'pending_escrow': pending_escrow,
        'active_pipeline_value': active_pipeline_value,
        'completed_payouts_count': completed_payouts_count,
        'approved_milestones_count': approved_milestones_count,
        'total_count': payments_qs.count(),
        'status_filter': status_filter,
        'active_contracts': active_contracts[:5],
        'earnings_chart_labels_json': json.dumps(earnings_chart_labels),
        'earnings_chart_data_json': json.dumps(earnings_chart_data),
    }
    return render(request, 'freelancer/earnings.html', context)


@login_required
def freelancer_my_reviews_view(request):
    """
    Freelancer's reputation and review management page (/freelancer/reviews/).
    Displays live aggregate metrics, category scores, breakdown bars, and paginated
    review stream with the ability to post one public response.
    """
    if getattr(request.user, 'profile', None) and request.user.profile.role == 'client':
        return redirect('client_reviews')

    user = request.user
    profile = getattr(user, 'profile', None)
    if profile:
        profile.recalculate_stats()

    sort = request.GET.get('sort', 'newest').strip()
    reviews_qs = Review.objects.filter(reviewee=user, is_hidden=False).select_related('reviewer', 'project', 'contract')

    if sort == 'highest':
        reviews_qs = reviews_qs.order_by('-overall_rating', '-created_at')
    elif sort == 'lowest':
        reviews_qs = reviews_qs.order_by('overall_rating', '-created_at')
    else:
        reviews_qs = reviews_qs.order_by('-created_at')

    # Rating breakdown counts (5, 4, 3, 2, 1 stars)
    total_reviews = reviews_qs.count()
    rating_breakdown = []
    for s in [5, 4, 3, 2, 1]:
        if s == 5:
            count = reviews_qs.filter(overall_rating__gte=4.5).count()
        elif s == 1:
            count = reviews_qs.filter(overall_rating__lt=2.0).count()
        else:
            count = reviews_qs.filter(overall_rating__gte=s - 0.5, overall_rating__lt=s + 0.5).count()
        pct = round((count / total_reviews) * 100) if total_reviews > 0 else 0
        rating_breakdown.append({
            'star': s,
            'count': count,
            'percent': pct
        })

    paginator = Paginator(reviews_qs, 5)
    page_num = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_num)

    reply_form = FreelancerReplyForm()

    context = {
        'profile': profile,
        'reviews': page_obj,
        'page_obj': page_obj,
        'total_reviews': total_reviews,
        'rating_breakdown': rating_breakdown,
        'sort': sort,
        'reply_form': reply_form,
    }
    return render(request, 'freelancer/my_reviews.html', context)


@login_required
@require_POST
def freelancer_review_reply_view(request, review_id):
    """
    POST endpoint allowing a freelancer to post one professional public reply
    to a client review on their profile.
    """
    review = get_object_or_404(Review, id=review_id, reviewee=request.user)

    if review.freelancer_reply:
        messages.warning(request, "You have already posted a response to this review.")
        return redirect('freelancer_my_reviews')

    form = FreelancerReplyForm(request.POST)
    if form.is_valid():
        review.freelancer_reply = form.cleaned_data['reply']
        review.replied_at = timezone.now()
        review.save(update_fields=['freelancer_reply', 'replied_at'])
        messages.success(request, "Your public response has been published successfully.")
    else:
        error_msg = form.errors.get('reply', ['Invalid reply text.'])[0]
        messages.error(request, error_msg)

    return redirect('freelancer_my_reviews')