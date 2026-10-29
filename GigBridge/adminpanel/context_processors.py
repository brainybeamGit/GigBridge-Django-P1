from client.models import ContactMessage


def admin_messages_badge(request):
    """
    Context processor that provides unread ('new') contact messages count
    for the admin panel navigation badges.
    """
    try:
        if request.user.is_authenticated and (
            request.user.is_staff or request.user.is_superuser or (
                getattr(request.user, 'profile', None) and request.user.profile.role == 'admin'
            )
        ):
            unread_count = ContactMessage.objects.filter(status='new').count()
            return {'unread_messages_count': unread_count}
    except Exception:
        pass
    return {'unread_messages_count': 0}
