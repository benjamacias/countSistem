from django import template
from urllib.parse import quote_plus

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css_class):
    return field.as_widget(attrs={**field.field.widget.attrs, "class": css_class})


@register.simple_tag
def maps_url(trip):
    addrs = (
        [trip.start_address]
        + list(trip.addresses.values_list("address", flat=True).order_by("order"))
        + [trip.end_address]
    )
    return "https://www.google.com/maps/dir/" + "/".join(
        quote_plus(a) for a in addrs if a
    )