from django import forms
from django.forms import inlineformset_factory
from .models import Trip, TripAddress, Payment
from .models import Client, Driver, Vehicle, Asesoramiento, Invoice
import re
from django import forms
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger('app')

TripAddressFormSet = inlineformset_factory(
    Trip,
    TripAddress,
    fields=("address", "order"),
    extra=1,
    can_delete=True,
)

class TripForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = "__all__"
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'start_address': forms.TextInput(attrs={'class': 'form-control'}),
            'end_address': forms.TextInput(attrs={'class': 'form-control'}),
            'products': forms.Textarea(attrs={'class': 'form-control'}),
            'departure_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'arrival_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'value': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'driver': forms.Select(attrs={'class': 'form-select', 'id': 'id_driver'}),
            'vehicle': forms.Select(attrs={'class': 'form-select', 'id': 'id_vehicle'}),
        }
    def __init__(self, *args, **kwargs):
        driver = kwargs.pop("driver", None)
        super().__init__(*args, **kwargs)

        if driver:
            self.fields["vehicle"].queryset = Vehicle.objects.filter(driver=driver)
            self.initial["driver"] = driver
            first_vehicle = Vehicle.objects.filter(driver=driver).first()
            if first_vehicle:
                self.initial["vehicle"] = first_vehicle

class PaymentForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        label="Cliente",
        required=True
    )

    # Campos para factura electrónica
    tipo_cbte = forms.ChoiceField(
        choices=[
            (1, "Factura A"),
            (6, "Factura B"),
            (11, "Factura C")
        ],
        label="Tipo de Comprobante",
        required=True
    )
    punto_venta = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Punto de Venta"
    )

    generar_factura = forms.BooleanField(
        label="¿Generar factura electrónica con AFIP?",
        required=False
    )

    class Meta:
        model = Payment
        fields = ["method", "amount", "client", "tipo_cbte", "punto_venta", "generar_factura"]

    def save(self, commit=True):
        payment = super().save(commit=False)

        if self.cleaned_data.get("generar_factura"):
            client = self.cleaned_data["client"]
            tipo_cbte = self.cleaned_data["tipo_cbte"]
            punto_venta = self.cleaned_data["punto_venta"]

            # Simulación de AFIP
            cae = "71345678901234"
            vencimiento_cae = "2025-06-10"

            invoice = Invoice.objects.create(
                trip=self.trip,
                amount=payment.amount,
                punto_venta=punto_venta,
                tipo_cbte=tipo_cbte,
                cae=cae,
                cae_vencimiento=vencimiento_cae
            )
            payment.invoice = invoice

        if commit:
            payment.save()

            invoice = payment.invoice
            logger.info(f"Factura creada: {invoice}")
            logger.info(f"estado del viaje: {invoice.trip.status if invoice.trip else 'No hay viaje asociado'}")

        return payment

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'  # O pon los campos específicos que quieras

class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "description"]
        
    def clean_plate(self):
        plate = self.cleaned_data.get("plate", "").upper().replace(" ", "")
        pattern1 = r'^[A-Z]{3}\d{3}$'
        pattern2 = r'^\d{2}[A-Z]{3}\d{2}$'

        if plate:
            if not re.fullmatch(pattern1, plate) and not re.fullmatch(pattern2, plate):
                raise ValidationError("Formato de patente inválido. Use XXX000 o 00XXX00.")
            
            # Verifica si ya existe un vehículo con esa patente
            if Vehicle.objects.filter(plate=plate).exists():
                raise ValidationError("Esa patente ya está registrada.")
        
        return plate

class AssignVehiclesForm(forms.ModelForm):
    vehicles = forms.ModelMultipleChoiceField(
        queryset=Vehicle.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Vehículos disponibles"
    )

    class Meta:
        model = Driver
        fields = ["name", "vehicles"]

class DriverForm(forms.ModelForm):
    vehicles = forms.ModelMultipleChoiceField(
        queryset=Vehicle.objects.filter(driver__isnull=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Vehículos a asignar"
    )

    class Meta:
        model = Driver
        fields = ["name", "surname", "dni", "gmail", "phone", "address", "license_number"]

    def save(self, commit=True):
        driver = super().save(commit=False)
        if commit:
            driver.save()
            vehicles = self.cleaned_data.get("vehicles")
            for vehicle in vehicles:
                vehicle.driver = driver
                vehicle.save()
        return driver


class VehicleInlineForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "description"]



class DriverWithVehicleForm(forms.ModelForm):
    plate = forms.CharField(label="Patente del Vehículo", required=False)
    description = forms.CharField(label="Descripción del Vehículo", required=False)

    class Meta:
        model = Driver
        fields = ["name", "surname", "dni", "gmail", "phone", "address", "license_number"]

    def clean_plate(self):
        plate = self.cleaned_data.get("plate", "").upper().replace(" ", "")
        pattern1 = r'^[A-Z]{3}\d{3}$'
        pattern2 = r'^\d{2}[A-Z]{3}\d{2}$'

        if plate:
            if not re.fullmatch(pattern1, plate) and not re.fullmatch(pattern2, plate):
                raise ValidationError("Formato de patente inválido. Use XXX000 o 00XXX00.")
            if Vehicle.objects.filter(plate=plate).exists():
                raise ValidationError("Esa patente ya está registrada.")
        
        return plate

    def save(self, commit=True):
        driver = super().save(commit=commit)
        plate = self.cleaned_data.get("plate")
        description = self.cleaned_data.get("description")

        if plate:
            Vehicle.objects.create(plate=plate, description=description, driver=driver)

        return driver

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'

class AsesoramientoForm(forms.ModelForm):
    class Meta:
        model = Asesoramiento
        fields = '__all__'

