from django import template

from store.formatting import format_inr

register = template.Library()


@register.filter
def inr(value):
    return format_inr(value)


@register.filter
def star_active(star_number, rating):
    """Return True for stars included in the nearest whole-star visual rating."""
    try:
        return int(star_number) <= int(float(rating) + 0.5)
    except (TypeError, ValueError):
        return False
