"""Custom template tags for web app."""
from django import template

register = template.Library()


@register.filter
def get_item(d, key):
    """Get item from dict by key. Returns [] if key not found."""
    if d is None:
        return []
    return d.get(key, [])


@register.filter
def date_lt(d, other):
    """Return True if d < other (for date comparison)."""
    if d is None or other is None:
        return False
    return d < other


@register.filter
def date_gte(d, other):
    """Return True if d >= other (for date comparison)."""
    if d is None or other is None:
        return False
    return d >= other
