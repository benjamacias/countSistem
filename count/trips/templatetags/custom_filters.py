from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def sum_field(queryset, field_name):
    return sum(getattr(item, field_name, 0) for item in queryset)

