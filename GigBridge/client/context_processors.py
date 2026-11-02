from django.db.models import Q
from client.models import Message
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
    - active_currency: 'INR' or 'USD'
    - user_currency: 'INR' or 'USD' (alias for full backward compatibility)
    - currency_symbol: '₹' or '$'
    - is_usd: boolean (True if USD)
    - usd_inr_rate: current exchange rate float
    - show_complete_profile_prompt: True if existing user has empty country/phone
    """
    curr = resolve_currency_for_user_or_request(request=request)
    rate = get_usd_inr_rate()
    symbol = '₹' if curr == 'INR' else '$'

    show_complete_profile_prompt = False
    if getattr(request, 'user', None) and request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile and (not profile.country or not profile.phone_number):
            show_complete_profile_prompt = True

    return {
        'active_currency': curr,
        'user_currency': curr,
        'currency_symbol': symbol,
        'is_usd': (curr == 'USD'),
        'usd_inr_rate': float(rate),
        'show_complete_profile_prompt': show_complete_profile_prompt,
    }
