from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, DetailView
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy
from django.db import transaction
from .models import Trip, Invoice, Client, Driver, Vehicle
from .forms import TripForm, TripAddressFormSet, PaymentForm, ClientForm, DriverForm, VehicleForm, AsesoramientoForm
from .forms import DriverWithVehicleForm
from django.contrib import messages
from .models import Client, Asesoramiento
from .forms import ClienteForm, AsesoramientoForm, AssignVehiclesForm
from django.http import JsonResponse
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Prefetch
from django.db.models.functions import Concat
from django.db.models import Value

ADDRESS_PREFIX = "addresses" 


def get_vehicles_by_driver(request):
    driver_id = request.GET.get("driver_id")
    vehicles = Vehicle.objects.filter(driver_id=driver_id)

    data = [
        {"id": vehicle.id, "plate": vehicle.plate, "description": vehicle.description}
        for vehicle in vehicles
    ]
    return JsonResponse(data, safe=False)

@method_decorator(login_required, name="dispatch")
class ClientListView(ListView):
    model = Client
    template_name = "clients/client_list.html"
    context_object_name = "clients"



@method_decorator(login_required, name="dispatch")
class TripListView(ListView):
    model = Trip
    template_name = "trips/trip_dashboard.html"
    context_object_name = "trips"
    paginate_by = 6

    def get_queryset(self):
        qs = Trip.objects.select_related("client", "driver", "vehicle").order_by("-id")

        qs = qs.prefetch_related(
            Prefetch('invoices', queryset=Invoice.objects.order_by('id'))
        )

        q = self.request.GET.get("q")
        if q:
            qs = qs.annotate(
                full_name=Concat("client__nombre", Value(" "), "client__apellido")
            ).filter(
                Q(full_name__icontains=q) |
                Q(client__nombre__icontains=q) |
                Q(driver__name__icontains=q) |
                Q(vehicle__plate__icontains=q) |
                Q(id__icontains=q) |
                Q(start_address__icontains=q) |
                Q(end_address__icontains=q)
            )

        cliente_id = self.request.GET.get("cliente_id")
        if cliente_id:
            qs = qs.filter(client__id=cliente_id)

        status = self.request.GET.getlist("status")
        if status:
            qs = qs.filter(status__in=status)

        valor_min = self.request.GET.get("valor_min")
        if valor_min:
            qs = qs.filter(value__gte=valor_min)

        facturado = self.request.GET.get("facturado")
        if facturado == "1":
            qs = qs.filter(invoices__isnull=False)
        elif facturado == "0":
            qs = qs.filter(invoices__isnull=True)

        return qs

    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for trip in context['trips']:
            trip.first_invoice = trip.invoices.first()  # Agregamos el primer invoice al viaje
        return context

@method_decorator(login_required, name="dispatch")
class TripCreateView(CreateView):
    model = Trip
    form_class = TripForm
    template_name = "trips/trip_form.html"
    success_url = reverse_lazy("trips:trip_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        driver_id = self.request.GET.get("driver") or self.request.POST.get("driver")

        if driver_id:
            try:
                driver = Driver.objects.get(id=driver_id)
                kwargs["driver"] = driver
            except Driver.DoesNotExist:
                pass

        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        driver_id = self.request.GET.get("driver") or self.request.POST.get("driver")
        if driver_id:
            try:
                driver = Driver.objects.get(id=driver_id)
                form.fields["vehicle"].queryset = Vehicle.objects.filter(driver=driver)
                form.initial["driver"] = driver
                first_vehicle = Vehicle.objects.filter(driver=driver).first()
                if first_vehicle:
                    form.initial["vehicle"] = first_vehicle
            except Driver.DoesNotExist:
                pass
        return form
    # -------- context --------
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["addresses"] = TripAddressFormSet(
                self.request.POST,
                prefix=ADDRESS_PREFIX            
            )
        else:
            context["addresses"] = TripAddressFormSet(
                prefix=ADDRESS_PREFIX
            )
        return context

    # -------- guardar --------
    def form_valid(self, form):
        context = self.get_context_data()
        addresses = context["addresses"]

        with transaction.atomic():
            self.object = form.save()
            # Important: ligar el formset al viaje antes de validar/guardar
            addresses.instance = self.object

            if addresses.is_valid():
                addresses.save()
            else:
                # Si el formset falla, volver a mostrar errores
                return self.form_invalid(form)

        return super().form_valid(form)
    
    
@login_required
def trip_complete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    trip.status = "recibido"
    trip.save()
    invoice, created = Invoice.objects.get_or_create(trip=trip, defaults={"amount": trip.value})
    return redirect("trips:invoice_detail", pk=invoice.id)

@method_decorator(login_required, name="dispatch")
class InvoiceDetailView(DetailView):
    model = Invoice
    template_name = "trips/invoice_detail.html"
    context_object_name = "invoice"

@login_required
def payment_create(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    paid = sum(p.amount for p in invoice.payments.all())  # ← uso de invoice.payments
    remaining = invoice.amount - paid                     # ← amount, no total

    if request.method == "POST":
        form = PaymentForm(request.POST)
        form = PaymentForm(initial={
            "client": invoice.trip.client if invoice.trip else None
        })
        if form.is_valid():
            amount = form.cleaned_data["amount"]
            if amount > remaining:
                form.add_error("amount", "No puede pagar más de lo que resta.")
            else:
                payment = form.save(commit=False)
                payment.invoice = invoice
                payment.save()
                
                if invoice and invoice.trip and invoice.remaining() <= 0:
                    print("Factura pagada completamente, actualizando estado del viaje...")
                    invoice.trip.status = "facturado"
                    invoice.trip.save()

                return redirect("trips:invoice_detail", invoice.id)
    else:
        form = PaymentForm()
        form = PaymentForm(initial={
            "client": invoice.trip.client if invoice.trip else None
        })
    return render(
        request,
        "trips/payment_form.html",
        {"form": form, "invoice": invoice, "remaining": remaining},
    )


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("clients_list")  # Cambia a la URL que uses para listar clientes
    else:
        form = ClientForm()
    return render(request, "clients/client_form.html", {"form": form})


@method_decorator(login_required, name="dispatch")
class DriverListView(ListView):
    model = Driver
    template_name = "drivers/driver_list.html"
    context_object_name = "drivers"

def drivers_list(request):
    drivers = Driver.objects.prefetch_related('vehicle_set').all()
    return render(request, 'drivers/driver_list.html', {'drivers': drivers})

@login_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("trips:drivers_list")
    else:
        form = VehicleForm()
    return render(request, "vehicles/vehicle_form.html", {"form": form})

@login_required
def driver_create(request):
    if request.method == "POST":
        form = DriverWithVehicleForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("trips:drivers_list")
    else:
        form = DriverWithVehicleForm()
    return render(request, "drivers/driver_form.html", {"form": form})

@method_decorator(login_required, name="dispatch")
class InvoiceListView(ListView):
    model = Invoice
    template_name = "trips/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 6

    def get_queryset(self):
        queryset = Invoice.objects.select_related("trip", "trip__client").order_by("-id")
        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(trip__client__nombre__icontains=q) |
                Q(trip__id__icontains=q)
            )
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice_totals = {}

        for invoice in context["invoices"]:
            trip = invoice.trip
            if hasattr(trip, "invoices"):
                total = trip.invoices.aggregate(total=Sum("amount"))["total"] or 0
            else:
                total = invoice.amount
            invoice_totals[invoice.id] = total

        context["invoice_totals"] = invoice_totals
        return context
    

@method_decorator(login_required, name='dispatch')
class VehicleListView(ListView):
    model = Vehicle
    template_name = 'vehicles/vehicle_list.html'
    context_object_name = 'vehicles'
    paginate_by = 6

    def get_paginate_by(self, queryset):
        try:
            return int(self.request.GET.get('limit', paginate_by=self.paginate_by))
        except (ValueError, TypeError):
            paginate_by=self.paginate_by
            return paginate_by  # fallback por defecto

    def get_queryset(self):
        qs = Vehicle.objects.select_related('driver')

        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(description__icontains=q) |
                Q(plate__icontains=q) |
                Q(driver__name__icontains=q)
            )

        orden = self.request.GET.get('orden')
        if orden == 'precio_asc':
            qs = qs.order_by('price_per_km')
        elif orden == 'precio_desc':
            qs = qs.order_by('-price_per_km')
        else:
            qs = qs.order_by('-id')

        return qs

    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

def trip_cancel(request, pk):
    trip = get_object_or_404(Trip, pk=pk)
    if trip.status != 'recibido':  # o el estado que consideres "completado"
        trip.status = 'cancelado'  # Asegurate de tener este estado en tu modelo
        trip.save()
        messages.success(request, f"El viaje #{trip.id} fue cancelado.")
    else:
        messages.warning(request, f"El viaje #{trip.id} ya fue completado y no puede cancelarse.")
    return redirect('trips:trip_list')  # Asegurate que 'trip_list' sea el nombre de tu vista de lista

def asesoramiento_create(request, cliente_id):
    cliente = get_object_or_404(Client, id=cliente_id)
    if request.method == 'POST':
        form = AsesoramientoForm(request.POST)
        if form.is_valid():
            asesoramiento = form.save(commit=False)
            asesoramiento.cliente = cliente
            asesoramiento.save()
            return redirect('clients_list')
    else:
        form = AsesoramientoForm()
    return render(request, 'clients/form_asesoramiento.html', {'form': form, 'cliente': cliente})

@login_required
def assign_vehicles_to_driver(request, pk):
    driver = get_object_or_404(Driver, pk=pk)
    if request.method == "POST":
        form = AssignVehiclesForm(request.POST, instance=driver)
        if form.is_valid():
            form.save()
            return redirect("trips:drivers_list")
    else:
        form = AssignVehiclesForm(instance=driver)
    return render(request, "drivers/assign_vehicles.html", {"form": form, "driver": driver})

@login_required
def assign_vehicles(request, driver_id):
    driver = get_object_or_404(Driver, id=driver_id)
    vehicles = Vehicle.objects.all()

    if request.method == "POST":
        selected_ids = request.POST.getlist("vehicles")
        
        # Limpiar vehículos previamente asignados a este conductor
        Vehicle.objects.filter(driver=driver).update(driver=None)

        # Asignar nuevos
        Vehicle.objects.filter(id__in=selected_ids).update(driver=driver)
        
        return redirect("drivers_list")  # o el nombre correcto de tu url

    return render(request, "drivers/assign_vehicles.html", {
        "driver": driver,
        "vehicles": vehicles,
    })