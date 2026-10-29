from django import template
from django.utils.safestring import mark_safe
from client.helpers import can_message, can_message_conversation
from client.models import Proposal, Contract

register = template.Library()


@register.simple_tag
def can_message_check(user, project, other_user=None):
    """
    Template tag to check whether messaging is permitted on a project.
    {% can_message_check request.user project as allowed %}
    """
    return can_message(user, project, other_user)


@register.filter
def can_message_proposal(proposal, user):
    """
    Filter to check whether a proposal allows messaging for user.
    Usage: {% if proposal|can_message_proposal:request.user %}
    """
    if not proposal or not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if proposal.status != 'accepted':
        return False
    return user.id in [proposal.project.client_id, proposal.freelancer_id]


@register.simple_tag
def can_view_private_info(client_user, freelancer_user):
    """
    Rule: Hide private data (email, phone) until a proposal is accepted between client and freelancer.
    """
    if not client_user or not client_user.is_authenticated or not freelancer_user:
        return False
    if client_user.is_superuser or client_user.id == freelancer_user.id:
        return True
    # Check if there is an accepted proposal or contract between them
    has_accepted_proposal = Proposal.objects.filter(
        project__client=client_user,
        freelancer=freelancer_user,
        status='accepted'
    ).exists()
    has_contract = Contract.objects.filter(
        client=client_user,
        freelancer=freelancer_user
    ).exists()
    return has_accepted_proposal or has_contract


@register.simple_tag
def render_stars(rating):
    """
    Renders 5 Bootstrap Icons stars (full, half, empty) from a float or int rating.
    """
    try:
        val = float(rating or 0.0)
    except (ValueError, TypeError):
        val = 0.0

    html = []
    for i in range(1, 6):
        if val >= i:
            html.append('<i class="bi bi-star-fill text-warning"></i>')
        elif val >= (i - 0.5):
            html.append('<i class="bi bi-star-half text-warning"></i>')
        else:
            html.append('<i class="bi bi-star text-muted opacity-50"></i>')
    return mark_safe(' '.join(html))
