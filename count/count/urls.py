from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from trips import views
from trips.views import InvoiceListView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin y autenticación
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("invoices/", InvoiceListView.as_view(), name="invoice_list"),


    # Clientes
    path("clients/", views.ClientListView.as_view(), name="clients_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<int:cliente_id>/asesoramiento/", views.asesoramiento_create, name="asesoramiento_create"),

    # Conductores
    path("drivers/", views.DriverListView.as_view(), name="drivers_list"),
    path("drivers/new/", views.driver_create, name="driver_create"),
    path("drivers/<int:driver_id>/assign/", views.assign_vehicles, name="assign_vehicles"),

    # Vehículos
    path("vehicles/new/", views.vehicle_create, name="vehicle_create"),
    
    # Viajes
    path("trips/new/", views.TripCreateView.as_view(), name="trip_create"),
   
    # App principal (trips.urls)
    path("", include("trips.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
