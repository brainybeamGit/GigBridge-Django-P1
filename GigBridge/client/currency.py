import re
import threading
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.cache import cache

# Thread-local storage to capture the current request seamlessly
_thread_locals = threading.local()


def set_current_request(request):
    """Stores the active request for the current thread."""
    _thread_locals.request = request


def get_current_request():
    """Retrieves the active request for the current thread, or None."""
    return getattr(_thread_locals, 'request', None)


def get_currency_for_country(country_code):
    """
    Rule:
    - If the user's country is India ('IN'), show all prices in Indian Rupees (₹, INR).
    - For every other country, show all prices in US Dollars ($, USD).
    """
    if str(country_code or '').strip().upper() == 'IN':
        return 'INR'
    return 'USD'


def get_usd_inr_rate():
    """
    Returns the current USD to INR exchange rate.
    Tries cache first, then ExchangeRate model, then settings.USD_INR_RATE (default 83.0).
    Never raises an exception or fails a page.
    """
    cached = cache.get('usd_inr_rate')
    if cached is not None:
        try:
            return Decimal(str(cached))
        except Exception:
            pass

    try:
        from client.models import ExchangeRate
        obj = ExchangeRate.objects.filter(from_currency='USD', to_currency='INR').first()
        if obj and obj.rate and obj.rate > 0:
            cache.set('usd_inr_rate', float(obj.rate), 3600)
            return obj.rate
    except Exception:
        pass

    fallback = getattr(settings, 'USD_INR_RATE', 83.0)
    try:
        return Decimal(str(fallback))
    except Exception:
        return Decimal('83.0000')


def convert_inr_to_usd(amount_inr, rate=None):
    """
    Converts an amount from base INR to USD.
    """
    if amount_inr is None or amount_inr == '':
        return Decimal('0.00')
    try:
        amt = Decimal(str(amount_inr))
    except Exception:
        return Decimal('0.00')

    r = Decimal(str(rate)) if rate else get_usd_inr_rate()
    if r <= Decimal('0'):
        r = Decimal('83.0000')
    return (amt / r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def convert_usd_to_inr(amount_usd, rate=None):
    """
    Converts an amount from USD to base INR.
    """
    if amount_usd is None or amount_usd == '':
        return Decimal('0.00')
    try:
        amt = Decimal(str(amount_usd))
    except Exception:
        return Decimal('0.00')

    r = Decimal(str(rate)) if rate else get_usd_inr_rate()
    if r <= Decimal('0'):
        r = Decimal('83.0000')
    return (amt * r).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def format_inr(amount, include_symbol=True, decimals=None):
    """
    Formats an INR amount using the official Indian digit grouping system:
    Last 3 digits grouped, then pairs of 2 digits (e.g. ₹1,25,000, ₹10,00,000).
    Whole numbers are formatted with zero decimal places by default.
    """
    if amount is None or amount == '':
        return ''
    try:
        d = Decimal(str(amount))
    except Exception:
        return str(amount)

    is_negative = d < 0
    d = abs(d)

    is_whole = (d == d.to_integral())
    if decimals is None:
        dec_places = 0 if is_whole else 2
    else:
        dec_places = int(decimals)

    if dec_places > 0:
        d_rounded = d.quantize(Decimal('1.' + '0' * dec_places), rounding=ROUND_HALF_UP)
        s = f"{d_rounded:.{dec_places}f}"
        int_part, dec_part = s.split('.')
    else:
        int_part = str(int(d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
        dec_part = ""

    # Group according to Indian Numbering System
    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        formatted_int = ','.join(groups) + ',' + last3

    result = formatted_int
    if dec_part:
        result += '.' + dec_part
    if is_negative:
        result = '-' + result
    if include_symbol:
        result = '₹' + result
    return result


def format_usd(amount_in_usd, include_symbol=True, decimals=2):
    """
    Formats a USD amount using standard US formatting:
    e.g. $1,500.00 or $125,000.00.
    """
    if amount_in_usd is None or amount_in_usd == '':
        return ''
    try:
        d = Decimal(str(amount_in_usd))
    except Exception:
        return str(amount_in_usd)

    is_negative = d < 0
    d = abs(d)
    dec_places = int(decimals) if decimals is not None else 2

    d_rounded = d.quantize(Decimal('1.' + '0' * dec_places), rounding=ROUND_HALF_UP)
    formatted = f"{d_rounded:,.{dec_places}f}"
    if is_negative:
        formatted = '-' + formatted
    if include_symbol:
        formatted = '$' + formatted
    return formatted


def resolve_currency_for_user_or_request(user=None, request=None, currency_override=None):
    """
    Resolves the display currency ('INR' or 'USD') in strict priority order:
    1. Explicit currency_override ('INR' or 'USD')
    2. Manual switch cookie 'gb_currency' (overrides registration for display)
    3. Logged-in user's profile display_currency
    4. Guests:
       - Accept-Language header or saved country cookie ('IN' -> 'INR', otherwise 'USD')
    5. Fallback: 'USD'
    """
    if currency_override:
        curr = str(currency_override).strip().upper()
        if curr in ['INR', 'USD']:
            return curr

    # Fall back to thread-local request if request not explicitly passed
    req = request or get_current_request()

    # 1. Manual choice cookie 'gb_currency' takes precedence for display
    if req and hasattr(req, 'COOKIES'):
        cookie_curr = req.COOKIES.get('gb_currency', '').strip().upper()
        if cookie_curr in ['INR', 'USD']:
            return cookie_curr

    # 2. Logged-in user profile display_currency
    target_user = user
    if not target_user and req and hasattr(req, 'user'):
        target_user = req.user

    if target_user and hasattr(target_user, 'is_authenticated') and target_user.is_authenticated:
        profile = getattr(target_user, 'profile', None)
        if profile and profile.display_currency:
            return profile.display_currency

    # 3. Guests: check country cookie or Accept-Language header
    if req:
        country_cookie = req.COOKIES.get('gb_country', '').strip().upper()
        if country_cookie == 'IN':
            return 'INR'

        accept_lang = req.META.get('HTTP_ACCEPT_LANGUAGE', '').upper()
        if re.search(r'[-_]IN\b', accept_lang):
            return 'INR'
        elif accept_lang:
            return 'USD'

    return 'USD'
