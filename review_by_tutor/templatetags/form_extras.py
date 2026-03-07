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

@register.simple_tag(takes_context=True)
def sort_url(context, field_name):
    request = context["request"]
    query = request.GET.copy()

    current_sort = query.get("sort", "")

    if current_sort == field_name:
        query["sort"] = f"-{field_name}"
    elif current_sort == f"-{field_name}":
        query["sort"] = field_name
    else:
        query["sort"] = field_name

    if "page" in query:
        query.pop("page")

    return "?" + query.urlencode()


@register.simple_tag(takes_context=True)
def sort_icon(context, field_name):
    request = context["request"]
    current_sort = request.GET.get("sort", "")

    if current_sort == field_name:
        return "↑"
    if current_sort == f"-{field_name}":
        return "↓"
    return ""


@register.simple_tag(takes_context=True)
def page_url(context, page_number):
    request = context["request"]
    query = request.GET.copy()
    query["page"] = page_number
    return "?" + query.urlencode()

