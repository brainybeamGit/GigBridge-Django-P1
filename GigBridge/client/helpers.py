"""
Security and permission helper functions for GigBridge messaging and access controls.
"""
from client.models import Proposal, Contract


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
