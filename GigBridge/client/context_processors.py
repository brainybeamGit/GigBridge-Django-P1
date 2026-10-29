from client.models import Message, Conversation
from django.db.models import Q


def unread_messages_count(request):
    """
    Context processor returning unread incoming message count for the authenticated user.
    Available across all templates as {{ unread_messages_count }}.
    """
    if not request.user.is_authenticated:
        return {'unread_messages_count': 0}

    user = request.user
    count = Message.objects.filter(
        Q(conversation__participants=user) |
        Q(conversation__client=user) |
        Q(conversation__freelancer=user),
        is_read=False
    ).exclude(sender=user).distinct().count()

    return {'unread_messages_count': count}
