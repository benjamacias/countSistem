from django.urls import path
from . import views
from .views import (
    TripListView,
    TripCreateView,
    InvoiceDetailView,
    InvoiceListView,
    VehicleListView,
    ClientListView,
    DriverListView
)

app_name = "trips"

urlpatterns = [
    # Dashboard / inicio
    path("", TripListView.as_view(), name="trip_list"),
    path("ajax/get_vehicles_by_driver/", views.get_vehicles_by_driver, name="get_vehicles_by_driver"),

    # Viajes
    path("trips/new/", TripCreateView.as_view(), name="trip_create"),
    path("trips/<int:pk>/complete/", views.trip_complete, name="trip_complete"),
    path("trip/<int:pk>/cancel/", views.trip_cancel, name="trip_cancel"),

    # Facturas y pagos
    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("invoice/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoice/<int:pk>/pay/", views.payment_create, name="payment_create"),

    # Clientes
    path("clients/", ClientListView.as_view(), name="clients_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:cliente_id>/asesoramiento/", views.asesoramiento_create, name="asesoramiento_create"),

    # Conductores
    path("drivers/", DriverListView.as_view(), name="drivers_list"),
    path("drivers/new/", views.driver_create, name="driver_create"),
    path("drivers/<int:driver_id>/assign/", views.assign_vehicles, name="assign_vehicles"),

    # Vehículos
    path("vehicles/", VehicleListView.as_view(), name="vehicles_list"),
    path("vehicles/new/", views.vehicle_create, name="vehicle_create"),
]
