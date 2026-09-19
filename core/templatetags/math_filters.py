from django import template
from decimal import Decimal

register = template.Library()

@register.filter(name='times')
def times(value, arg):
    """Multiplies the value by the arg."""
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError):
        return ''

@register.filter(name='div')
def div(value, arg):
    """Divides the value by the arg."""
    try:
        return Decimal(str(value)) / Decimal(str(arg))
    except (ValueError, TypeError, ZeroDivisionError):
        return ''

