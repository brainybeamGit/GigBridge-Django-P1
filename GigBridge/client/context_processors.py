from client.models import Message, Conversation
from django.db.models import Q
from client.currency import resolve_currency_for_user_or_request, get_usd_inr_rate


def unread_messages_count(request):
    """
    Context processor returning unread incoming message count for the authenticated user.
    Available across all templates as {{ unread_messages_count }}.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'unread_messages_count': 0}

    user = request.user
    count = Message.objects.filter(
        Q(conversation__participants=user) |
        Q(conversation__client=user) |
        Q(conversation__freelancer=user),
        is_read=False
    ).exclude(sender=user).distinct().count()

    return {'unread_messages_count': count}


def currency_context(request):
    """
    Context processor providing active currency information globally across all templates:
    - user_currency: 'INR' or 'USD'
    - currency_symbol: '₹' or '$'
    - is_usd: boolean
    - usd_inr_rate: current exchange rate float
    """
    curr = resolve_currency_for_user_or_request(request=request)
    rate = get_usd_inr_rate()
    return {
        'user_currency': curr,
        'currency_symbol': '₹' if curr == 'INR' else '$',
        'is_usd': (curr == 'USD'),
        'usd_inr_rate': float(rate),
    }
