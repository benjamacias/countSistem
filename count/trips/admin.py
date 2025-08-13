from django.contrib import admin
from .models import Client, Vehicle, Driver, Trip, TripAddress, Invoice, Payment, BillingError

# Inline para TripAddress dentro de Trip
class TripAddressInline(admin.TabularInline):
    model = TripAddress
    extra = 0

# Admin para Trip
@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    inlines = [TripAddressInline]
    list_display = ("id", "client", "driver", "vehicle", "status", "value")
    list_filter = ("status",)

# Registro simple para otros modelos
admin.site.register([Client, Vehicle, Driver, Invoice, Payment, BillingError])

# Admin para TripAddress, mostrando info propia y datos relacionados de Trip
@admin.register(TripAddress)
class TripAddressAdmin(admin.ModelAdmin):
    list_display = ("id", "address", "order", "get_trip_client", "get_trip_driver", "get_trip_vehicle", "get_trip_status", "get_trip_value")

    def get_trip_client(self, obj):
        return obj.trip.client
    get_trip_client.short_description = "Client"
    get_trip_client.admin_order_field = "trip__client"

    def get_trip_driver(self, obj):
        return obj.trip.driver
    get_trip_driver.short_description = "Driver"
    get_trip_driver.admin_order_field = "trip__driver"

    def get_trip_vehicle(self, obj):
        return obj.trip.vehicle
    get_trip_vehicle.short_description = "Vehicle"
    get_trip_vehicle.admin_order_field = "trip__vehicle"

    def get_trip_status(self, obj):
        return obj.trip.status
    get_trip_status.short_description = "Status"
    get_trip_status.admin_order_field = "trip__status"

    def get_trip_value(self, obj):
        return obj.trip.value
    get_trip_value.short_description = "Value"
    get_trip_value.admin_order_field = "trip__value"
