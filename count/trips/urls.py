from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings

from .views import (
    TripListView,
    TripCreateView,
    InvoiceDetailView,
    InvoiceListView,
    VehicleListView,
    ClientListView,
    DriverListView,
    driver_edit,
    DriverAdvanceCreateView,
    DriverAdvanceListView
    
)

app_name = "trips"

urlpatterns = [
    # Dashboard / inicio
    path("", TripListView.as_view(), name="trip_list"),
    path("ajax/get_vehicles_by_driver/", views.get_vehicles_by_driver, name="get_vehicles_by_driver"),
    path("ajax/get_product_price/", views.get_product_price, name="get_product_price"),
    path("charts/", views.charts_view, name="charts"),

    
    # Viajes
    path("trips/new/", TripCreateView.as_view(), name="trip_create"),
    path("trips/<int:pk>/complete/", views.trip_complete, name="trip_complete"),
    path("trip/<int:pk>/cancel/", views.trip_cancel, name="trip_cancel"),

    # Facturas y pagos
    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),
    path("invoice/<int:pk>/", InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoice/<int:pk>/pay/", views.payment_create, name="payment_create"),
    path("nuevo/<int:driver_id>/", DriverAdvanceCreateView.as_view(), name="create"),
    path("lista/", DriverAdvanceListView.as_view(), name="list"),

    # Clientes
    path("clients/", ClientListView.as_view(), name="clients_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clientes/<int:pk>/editar/", views.client_update, name="client_update"),
    path("clients/<int:cliente_id>/asesoramiento/", views.asesoramiento_create, name="asesoramiento_create"),

    # Conductores
    path("drivers/", DriverListView.as_view(), name="drivers_list"),
    path("drivers/new/", views.driver_create, name="driver_create"),
    path("drivers/<int:driver_id>/assign/", views.assign_vehicles, name="assign_vehicles"),
    path('drivers/<int:pk>/edit/', driver_edit, name='driver_edit'),
    path("direccion/nueva/", views.empty_address_form, name="empty_address_form"),


    # Vehículos
    path("vehicles/", VehicleListView.as_view(), name="vehicles_list"),
    path("vehicles/new/", views.vehicle_create, name="vehicle_create"),

    #Productos
    path('productos/', views.product_list, name='product_list'),
    path('productos/nuevo/', views.product_create, name='product_create'),
    path('productos/<int:pk>/editar/', views.product_update, name='product_update'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
