from django import template

register = template.Library()

@register.filter
def get_field(form, name):
    if not hasattr(form, "fields"):
        return None
    try:
        return form[name]
    except KeyError:
        return None