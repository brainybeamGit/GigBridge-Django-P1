from django import template
from django.utils.safestring import mark_safe
from decimal import Decimal
from django.utils import timezone

register = template.Library()


@register.simple_tag
def render_stars(rating, max_stars=5):
    """
    Renders Bootstrap Icons stars (full, half, empty) from float/decimal/int rating.
    Usage: {% render_stars review.overall_rating %}
    """
    try:
        val = float(rating or 0.0)
    except (ValueError, TypeError):
        val = 0.0

    html = []
    for i in range(1, int(max_stars) + 1):
        if val >= i:
            html.append('<i class="bi bi-star-fill text-warning"></i>')
        elif val >= (i - 0.5):
            html.append('<i class="bi bi-star-half text-warning"></i>')
        else:
            html.append('<i class="bi bi-star text-muted opacity-50"></i>')
    return mark_safe(' '.join(html))


@register.filter
def reviewer_display_name(user):
    """
    Displays reviewer name as 'First name and last initial' (e.g., 'Rahul S.')
    Usage: {{ review.reviewer|reviewer_display_name }}
    """
    if not user:
        return "Verified Client"
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    if first and last:
        return f"{first} {last[0].upper()}."
    if first:
        return first
    username = user.username or ''
    if len(username) > 3:
        return f"{username[:3].capitalize()}***"
    return username


@register.filter
def split_tags(tags_str):
    """Splits a comma-separated tag string into a clean list."""
    if not tags_str:
        return []
    return [t.strip() for t in str(tags_str).split(',') if t.strip()]


@register.filter
def is_editable_review(review):
    """Returns True if the review was created <= 7 days ago."""
    if not review or not review.created_at:
        return True
    return (timezone.now() - review.created_at).total_seconds() <= 7 * 86400


@register.simple_tag
def calculate_percent(count, total):
    """Calculates integer percentage for progress bar."""
    try:
        c = int(count or 0)
        t = int(total or 0)
        if t <= 0:
            return 0
        return round((c / t) * 100)
    except Exception:
        return 0
