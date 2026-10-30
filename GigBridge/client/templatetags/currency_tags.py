from django import template
from django.utils.safestring import mark_safe
from decimal import Decimal
from client.currency import (
    resolve_currency_for_user_or_request,
    convert_inr_to_usd,
    format_inr,
    format_usd,
    get_usd_inr_rate,
    get_current_request
)

register = template.Library()


@register.filter(name='user_currency')
def user_currency_filter(user_or_request):
    """Returns 'INR' or 'USD' for the given user, request, or string."""
    if isinstance(user_or_request, str) and user_or_request.upper() in ['INR', 'USD']:
        return user_or_request.upper()
    return resolve_currency_for_user_or_request(user=user_or_request)


@register.filter(name='currency_symbol')
def currency_symbol_filter(user_or_request_or_code):
    """Filter returning '₹' or '$': e.g. {{ request.user|currency_symbol }}"""
    curr = user_currency_filter(user_or_request_or_code)
    return '₹' if curr == 'INR' else '$'


@register.simple_tag(takes_context=True, name='currency_symbol')
def currency_symbol_tag(context):
    """Tag returning the active currency symbol: {% currency_symbol %}"""
    req = context.get('request') or get_current_request()
    curr = resolve_currency_for_user_or_request(request=req)
    return '₹' if curr == 'INR' else '$'


@register.filter(name='money')
def money_filter(amount, user_or_request=None, decimals=None):
    """
    Template filter converting a base INR amount into the active display currency.
    Usage:
      {{ project.budget_min|money }}
      {{ contract.total_amount|money:request.user }}
      {{ milestone.amount|money:'USD' }}
      {{ payment.amount|money }}
    """
    if amount is None or amount == '':
        return ''

    # If target is None, resolve_currency_for_user_or_request picks up thread-local request
    req = user_or_request if hasattr(user_or_request, 'COOKIES') else None
    user = user_or_request if hasattr(user_or_request, 'is_authenticated') else None
    override = user_or_request if isinstance(user_or_request, str) else None

    curr = resolve_currency_for_user_or_request(user=user, request=req, currency_override=override)

    try:
        amt = Decimal(str(amount))
    except Exception:
        return str(amount)

    if curr == 'USD':
        rate = get_usd_inr_rate()
        usd_val = convert_inr_to_usd(amt, rate=rate)
        dec = 2 if decimals is None else int(decimals)
        return format_usd(usd_val, include_symbol=True, decimals=dec)
    else:
        return format_inr(amt, include_symbol=True, decimals=decimals)


@register.simple_tag(takes_context=True, name='money')
def money_tag(context, amount, user_or_curr=None, decimals=None):
    """
    Simple tag version of money filter:
    {% money amount %}
    {% money amount request.user %}
    """
    target = user_or_curr or context.get('request')
    return money_filter(amount, target, decimals=decimals)


@register.simple_tag(takes_context=True, name='money_range')
def money_range_tag(context, min_val, max_val, user_or_curr=None, budget_type='fixed'):
    """
    Formats a project budget range:
    {% money_range min max %}
    {% money_range min max request.user project.budget_type %}
    Produces:
      INR: ₹5,000 - ₹15,000 (or ₹500/hr)
      USD: $60.24 - $180.72 (or $6.02/hr)
    """
    target = user_or_curr or context.get('request')
    req = target if hasattr(target, 'COOKIES') else None
    user = target if hasattr(target, 'is_authenticated') else None
    override = target if isinstance(target, str) else None

    curr = resolve_currency_for_user_or_request(user=user, request=req, currency_override=override)
    rate = get_usd_inr_rate()

    try:
        min_d = Decimal(str(min_val or 0))
    except Exception:
        min_d = Decimal('0')

    try:
        max_d = Decimal(str(max_val or 0))
    except Exception:
        max_d = Decimal('0')

    if curr == 'USD':
        usd_min = convert_inr_to_usd(min_d, rate=rate)
        usd_max = convert_inr_to_usd(max_d, rate=rate)
        s_min = format_usd(usd_min, include_symbol=True, decimals=2)
        s_max = format_usd(usd_max, include_symbol=True, decimals=2)
    else:
        s_min = format_inr(min_d, include_symbol=True)
        s_max = format_inr(max_d, include_symbol=True)

    suffix = "/hr" if budget_type == 'hourly' else ""

    if min_d > 0 and max_d > 0 and min_d != max_d:
        return f"{s_min} - {s_max}{suffix}"
    elif max_d > 0:
        return f"{s_max}{suffix}"
    elif min_d > 0:
        return f"{s_min}{suffix}"
    else:
        return f"{s_min}{suffix}"


@register.simple_tag(takes_context=True, name='contract_money')
def contract_money(context, contract, amount, user_or_curr=None, decimals=None):
    """
    Contract-locked currency conversion:
    Uses contract.exchange_rate_used so contract milestones never change when global rate fluctuates.
    Usage:
      {% contract_money contract milestone.amount %}
      {% contract_money contract milestone.amount request.user %}
    """
    target = user_or_curr or context.get('request')
    req = target if hasattr(target, 'COOKIES') else None
    user = target if hasattr(target, 'is_authenticated') else None
    override = target if isinstance(target, str) else None

    curr = resolve_currency_for_user_or_request(user=user, request=req, currency_override=override)

    if amount is None or amount == '':
        return ''

    try:
        amt = Decimal(str(amount))
    except Exception:
        return str(amount)

    if curr == 'USD':
        rate = getattr(contract, 'exchange_rate_used', None) or get_usd_inr_rate()
        usd_val = convert_inr_to_usd(amt, rate=rate)
        dec = 2 if decimals is None else int(decimals)
        return format_usd(usd_val, include_symbol=True, decimals=dec)
    else:
        return format_inr(amt, include_symbol=True, decimals=decimals)


@register.filter(name='contract_amount')
def contract_amount_filter(contract, amount_and_user):
    """
    Filter syntax for contract-locked amount:
    {{ contract|contract_amount:milestone.amount }}
    """
    return contract_money({}, contract, amount_and_user)


@register.simple_tag(takes_context=True, name='currency_note')
def currency_note(context, user_or_curr=None, text_only=False):
    """
    Displays a notice if the active currency is USD (since base accounting/charges are in INR):
    'Prices shown in USD (approx.)'
    """
    target = user_or_curr or context.get('request')
    curr = resolve_currency_for_user_or_request(user=target)
    if curr == 'USD':
        text = "Prices shown in USD (approx.)"
        if text_only:
            return text
        return mark_safe(f'<span class="gb-currency-note text-muted small" title="Base transactions are accounted in INR at the locked/current exchange rate">({text})</span>')
    return ""


@register.simple_tag(takes_context=True, name='query_transform')
def query_transform(context, **kwargs):
    """
    Returns the current request's query string with updated, added, or removed parameters.
    Passing a parameter as None, '', or False removes it from the query string.
    Properly URL-encodes all keys and values to prevent injection and breakages.
    Usage:
      <a href="?{% query_transform page=num %}">
      <a href="?{% query_transform category=None page=None %}">
    """
    request = context.get('request')
    if not request:
        return ''
    query_dict = request.GET.copy()
    for k, v in kwargs.items():
        if v is None or v == '' or v is False:
            query_dict.pop(k, None)
        else:
            query_dict[k] = str(v)
    return query_dict.urlencode()
