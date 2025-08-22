from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, DetailView
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy
from django.db import transaction
from .models import Trip, Invoice, Client, Driver, Vehicle, Product
from .forms import TripForm, TripAddressFormSet, PaymentForm, ClientForm, DriverForm, VehicleForm, AsesoramientoForm, CartaPorteForm
from .forms import DriverWithVehicleForm, ProductForm
from django.contrib import messages
from django.core.paginator import Paginator
from .models import Client, Asesoramiento
from .forms import ClienteForm, AsesoramientoForm, AssignVehiclesForm
from django.http import JsonResponse
from django.utils.http import urlencode
from django.db.models import Q
from django.db.models import Sum, Count
from django.db.models import Prefetch
from django.db.models.functions import Concat
from django.db.models import Value
from django.http import JsonResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from .forms import DriverForm, DriverAddressFormSet, DriverAdvanceFormSet, DriverAddressForm, DriverAdvanceForm, DriverAdvanceFormCreate
from django.http import HttpResponse
from django.views.generic.edit import UpdateView
from .models import Driver, Vehicle, DriverAddress, DriverAdvance
from django.conf import settings
from urllib.parse import quote_plus
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from decimal import Decimal
import json
from django.core.mail import EmailMessage
from .fact_arca import obtener_carta_porte


ADDRESS_PREFIX = "addresses" 


def get_vehicles_by_driver(request):
    driver_id = request.GET.get("driver_id")
    vehicles = Vehicle.objects.filter(driver_id=driver_id)

    data = [
        {"id": vehicle.id, "plate": vehicle.plate, "description": vehicle.description}
        for vehicle in vehicles
    ]
    return JsonResponse(data, safe=False)

def empty_address_form(request):
    total = request.GET.get("form_count", "__prefix__")
    form = DriverAddressForm(prefix=f"address-{total}")
    html = render_to_string("partials/address_form_htmx.html", {"form": form})
    return HttpResponse(html)

@require_GET
@csrf_exempt
def get_product_price(request):
    from .models import Product
    product_id = request.GET.get("product_id")
    try:
        product = Product.objects.get(id=product_id)
        return JsonResponse({"price_per_kilo": float(product.price_per_kilo)})
    except Product.DoesNotExist:
        return JsonResponse({"error": "Producto no encontrado"}, status=404)

def build_maps_url(trip):
        addresses = (
            [trip.start_address]
            + list(trip.addresses.values_list("address", flat=True).order_by("order"))
            + [trip.end_address]
        )
        return "https://www.google.com/maps/dir/" + "/".join(
            quote_plus(a) for a in addresses if a
        )


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
        context["products"] = Product.objects.all()
        context["google_maps_api_key"] = settings.GOOGLE_MAPS_API_KEY  # ← clave segura

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
    
    
@require_http_methods(["POST"])
@login_required
def trip_complete(request, pk):
    trip = get_object_or_404(Trip, pk=pk)

    try:
        received_weight = Decimal(request.POST.get("received_weight", "0"))
    except (TypeError, ValueError):
        messages.error(request, "Valor inválido para kilos recibidos.")
        return redirect("trips:trip_list")

    if received_weight < 0:
        messages.error(request, "El peso recibido no puede ser negativo.")
        return redirect("trips:trip_list")

    if received_weight > trip.total_weight:
        messages.error(request, "El peso recibido no puede ser mayor al peso total.")
        return redirect("trips:trip_list")
    
    # Calcular pérdida
    trip.status = "recibido"
    trip.received_weight =  received_weight
    trip.arrival_date = timezone.now()
    trip.save()

    # Crear factura si no existe
    invoice, created = Invoice.objects.get_or_create(
        trip=trip,
        defaults={"amount": trip.value}
    )
    return redirect("trips:invoice_detail", pk=invoice.id)


@method_decorator(login_required, name="dispatch")
class InvoiceDetailView(DetailView):
    model = Invoice
    template_name = "trips/invoice_detail.html"
    context_object_name = "invoice"


@login_required
def payment_create(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    paid = invoice.paid_total()
    remaining = invoice.amount - paid

    if request.method == "POST":
        form = PaymentForm(request.POST, initial={
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
                if getattr(form, "billing_error_message", None):
                    messages.warning(request, form.billing_error_message)

                # Si el monto pagado cubre el total de la factura, actualizamos estado del viaje
                if invoice.trip and invoice.remaining() <= 0:
                    invoice.trip.status = "facturado"
                    invoice.trip.save()

                return redirect("trips:invoice_detail", invoice.id)
    else:
        form = PaymentForm(initial={
            "client": invoice.trip.client if invoice.trip else None
        })

    return render(
        request,
        "trips/payment_form.html",
        {
            "form": form,
            "invoice": invoice,
            "remaining": remaining,
        }
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
class ClientListView(ListView):
    model = Client
    template_name = "clients/client_list.html"
    context_object_name = "clients"
    paginate_by = 6

def client_update(request, pk):
    cliente = get_object_or_404(Client, pk=pk)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=cliente)
        if form.is_valid():
            form.save()
            return redirect("clients_list")  # o a donde quieras volver
    else:
        form = ClientForm(instance=cliente)

    return render(request, "clients/client_edit.html", {"form": form, "cliente": cliente})

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
def carta_porte_invoice(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    if request.method == "POST":
        form = CartaPorteForm(request.POST, client=client)
        if form.is_valid():
            invoice = form.cleaned_data["invoice"]
            ctg = form.cleaned_data["ctg"]
            data = obtener_carta_porte(ctg)
            invoice.carta_porte_ctg = ctg
            invoice.carta_porte_pdf = data.get("pdf")

            action = request.POST.get("action")
            if action == "create_trip":
                plate = data.get("patente")
                try:
                    vehicle = Vehicle.objects.get(plate__iexact=plate)
                except Vehicle.DoesNotExist:
                    messages.error(request, "No se encontró vehículo con la patente indicada.")
                    return render(request, "trips/carta_porte_form.html", {"form": form, "client": client})
                if not vehicle.driver:
                    messages.error(request, "El vehículo no tiene chofer asignado.")
                    return render(request, "trips/carta_porte_form.html", {"form": form, "client": client})
                trip = Trip.objects.create(
                    client=client,
                    driver=vehicle.driver,
                    vehicle=vehicle,
                    start_address=data.get("origen", ""),
                    end_address=data.get("destino", ""),
                    total_weight=0,
                    value=0,
                    status="recibido",
                    arrival_date=timezone.now(),
                )
                invoice.trip = trip

            invoice.save()
            if client.gmail:
                email = EmailMessage(
                    subject="Carta de Porte",
                    body="Se adjunta Carta de Porte correspondiente.",
                    to=[client.gmail],
                )
                if data.get("pdf"):
                    email.attach("carta_porte.pdf", data["pdf"], "application/pdf")
                email.send(fail_silently=True)
            if action == "create_trip":
                messages.success(request, "Viaje generado y Carta de Porte vinculada.")
            else:
                messages.success(request, "Carta de Porte vinculada y enviada al cliente.")
            return redirect("trips:invoice_detail", invoice.pk)
    else:
        form = CartaPorteForm(client=client)
    return render(request, "trips/carta_porte_form.html", {"form": form, "client": client})

@method_decorator(login_required, name="dispatch")
class DriverListView(ListView):
    model = Driver
    ordering = ["name"]
    template_name = "drivers/driver_list.html"
    context_object_name = "drivers"
    paginate_by = 6

    def drivers_list(request):
        drivers = Driver.objects.prefetch_related('vehicle_set').all()
        return render(request, 'drivers/driver_list.html', {'drivers': drivers})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["driver_forms"] = {
            driver.id: DriverForm(instance=driver)
            for driver in context["drivers"]
        }
        return context
    
@login_required
def driver_edit(request, pk):
    driver = get_object_or_404(Driver, pk=pk)

    if request.method == "POST":
        form = DriverForm(request.POST, instance=driver)
        if form.is_valid():
            form.save()
            return redirect("trips:drivers_list")  # redirige a la lista de choferes
        else:
            # Opcional: si querés manejar errores, podés almacenarlos en messages o pasar por GET
            pass

    # Si alguien hace GET a esta URL, redirigimos a la lista
    return redirect("trips:drivers_list")

@login_required
def vehicle_create(request):
    if request.method == "POST":
        form = VehicleForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("trips:drivers_list")
    else:
        form = VehicleForm()
    return render(request, "vehicles/vehicle_form.html", {"form": form})

@login_required
def driver_create(request):
    if request.method == "POST":
        form = DriverForm(request.POST)
        address_formset = DriverAddressFormSet(request.POST, prefix='addresses')
        advance_formset = DriverAdvanceFormSet(request.POST, prefix='advances')

        if form.is_valid() and address_formset.is_valid() and advance_formset.is_valid():
            driver = form.save()

            # Asignar vehículos seleccionados
            vehicles = form.cleaned_data.get("vehicles")
            if vehicles:
                vehicles.update(driver=driver)

            # Guardar direcciones
            addresses = address_formset.save(commit=False)
            for address in addresses:
                address.driver = driver
                address.save()
            for obj in address_formset.deleted_objects:
                obj.delete()

            # Guardar anticipos
            advances = advance_formset.save(commit=False)
            for advance in advances:
                advance.driver = driver
                advance.save()
            for obj in advance_formset.deleted_objects:
                obj.delete()

            return redirect("trips:drivers_list")
    else:
        form = DriverForm()
        address_formset = DriverAddressFormSet(queryset=DriverAddress.objects.none(), prefix='addresses')
        advance_formset = DriverAdvanceFormSet(queryset=DriverAdvance.objects.none(), prefix='advances')

    return render(request, "drivers/driver_form.html", {
        "form": form,
        "address_formset": address_formset,
        "advance_formset": advance_formset,
    })

@method_decorator(login_required, name="dispatch")
class DriverAdvanceCreateView(CreateView):
    model = DriverAdvance
    form_class = DriverAdvanceFormCreate
    template_name = "advances/advance_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.driver = get_object_or_404(Driver, pk=kwargs.get("driver_id"))
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"driver": self.driver}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["driver"] = self.driver
        return context

    def form_valid(self, form):
        form.instance.driver = self.driver
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("trips:list")
    
@method_decorator(login_required, name="dispatch")
class DriverAdvanceListView(ListView):
    model = DriverAdvance
    template_name = "advances/advance_list.html"
    context_object_name = "advances"
    paginate_by = 6

    def get_ordering(self):
        orden = self.request.GET.get("orden", "-date")
        return orden

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_orden"] = self.request.GET.get("orden", "-date")
        context["params"] = urlencode({k: v for k, v in self.request.GET.items() if k != 'page'})
        return context
    

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
    max_paginate_by = 100

    def get_paginate_by(self, queryset):
        limit = self.request.GET.get('limit')
        if limit is None:
            return self.paginate_by
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            return self.paginate_by
        if limit <= 0 or limit > self.max_paginate_by:
            return self.paginate_by
        return limit
    
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

def product_list(request):
    product_queryset = Product.objects.all().order_by("id")
    paginator = Paginator(product_queryset, 2)  # ← 2 productos por página

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Creamos un diccionario con formularios por producto
    forms = {product.id: ProductForm(instance=product) for product in page_obj}

    context = {
        "products": page_obj,
        "forms": forms,
        "page_obj": page_obj,  # para usar en la paginación del template
        "is_paginated": page_obj.has_other_pages(),
    }
    return render(request, "products/product_list.html", context)


def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, instance=product)

    if request.method == "POST":
        if form.is_valid():
            form.save()
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            return redirect('trips:product_list')
        else:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                html = render_to_string('products/product_update_inline.html', {'form': form, 'product': product}, request=request)
                return HttpResponseBadRequest(html)

    return render(request, 'products/product_update_inline.html', {'form': form, 'product': product})


def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('trips:product_list')
    else:
        form = ProductForm()
    return render(request, 'products/product_form.html', {'form': form})


@login_required
def charts_view(request):
    invoice_summary = (
        Invoice.objects.values('created_at__month')
        .annotate(total=Sum('amount'))
        .order_by('created_at__month')
    )
    invoice_labels = [f"Mes {item['created_at__month']}" for item in invoice_summary]
    invoice_data = [float(item['total']) for item in invoice_summary]

    trip_summary = (
        Trip.objects.values('status')
        .annotate(total=Count('id'))
        .order_by('status')
    )
    trip_labels = [item['status'] for item in trip_summary]
    trip_data = [item['total'] for item in trip_summary]

    advance_summary = (
        DriverAdvance.objects.values('category')
        .annotate(total=Sum('amount'))
        .order_by('category')
    )
    advance_labels = [item['category'] for item in advance_summary]
    advance_data = [float(item['total']) for item in advance_summary]

    products = Product.objects.all()
    product_labels = [p.name for p in products]
    product_data = [float(p.price_per_kilo) for p in products]

    context = {
        'invoice_labels': json.dumps(invoice_labels),
        'invoice_data': json.dumps(invoice_data),
        'trip_labels': json.dumps(trip_labels),
        'trip_data': json.dumps(trip_data),
        'advance_labels': json.dumps(advance_labels),
        'advance_data': json.dumps(advance_data),
        'product_labels': json.dumps(product_labels),
        'product_data': json.dumps(product_data),
    }
    return render(request, 'charts/dashboard.html', context)

