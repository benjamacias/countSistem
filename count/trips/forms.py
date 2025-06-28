from django import forms
from django.forms import inlineformset_factory
from .models import Trip, TripAddress, Payment
from .models import Client, Driver, Vehicle, Asesoramiento, Invoice, Product, DriverAddress, DriverAdvance
import re
from django import forms
from django.core.exceptions import ValidationError
import logging
from django.forms import modelformset_factory
import datetime



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
            'departure_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'arrival_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'driver': forms.Select(attrs={'class': 'form-select', 'id': 'id_driver'}),
            'vehicle': forms.Select(attrs={'class': 'form-select', 'id': 'id_vehicle'}),
            'product': forms.Select(attrs={'class': 'form-select', 'id': 'id_product'}),
            'total_weight': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_total_weight'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_value'}),

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
        fields = ["method", "amount"]

    def save(self, commit=True, trip=None):
        payment = super().save(commit=False)

        if self.cleaned_data.get("generar_factura"):
            client = self.cleaned_data["client"]
            tipo_cbte = self.cleaned_data["tipo_cbte"]
            punto_venta = self.cleaned_data["punto_venta"]

            cae = "71345678901234"  # Simulación
            vencimiento_cae = datetime.date(2025, 6, 10)

            invoice = Invoice.objects.create(
                trip=trip,
                amount=payment.amount,
                punto_venta=punto_venta,
                tipo_cbte=tipo_cbte,
                cae=cae,
                cae_vencimiento=vencimiento_cae,
            )

            payment.invoice = invoice

        if commit:
            payment.save()

            if payment.invoice:
                logger.info(f"Factura creada: {payment.invoice}")
                if payment.invoice.trip:
                    logger.info(f"Estado del viaje: {payment.invoice.trip.status}")

        return payment

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'  # O pon los campos específicos que quieras

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["nombre", "apellido", "dni", "gmail", "domicilio", "telefono", "cuit", "tipo_iva"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "apellido": forms.TextInput(attrs={"class": "form-control"}),
            "dni": forms.NumberInput(attrs={"class": "form-control"}),
            "gmail": forms.EmailInput(attrs={"class": "form-control"}),
            "domicilio": forms.TextInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "cuit": forms.TextInput(attrs={"class": "form-control"}),
            "tipo_iva": forms.Select(attrs={"class": "form-select"}),
        }

class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "description", "driver", "image", "price_per_km"]
        
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
    class Meta:
        model = Driver
        fields = [
            "name",
            "surname",
            "dni",
            "gmail",
            "phone",
            "license_number",
            "license_expiry",
        ]
        widgets = {
            "license_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def save(self, commit=True):
        driver = super().save(commit=commit)
        return driver

class DriverAdvanceForm(forms.ModelForm):
    driver = forms.ModelChoiceField(
        queryset=Driver.objects.all(),
        label="Chofer",
        widget=forms.HiddenInput(),
        required=False  
    )

    category = forms.ChoiceField(
        choices=DriverAdvance.AdvanceCategory.choices,
        label="Categoría",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    amount = forms.DecimalField(
        label="Monto",
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej. 5000.00"})
    )

    description = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Opcional"})
    )

    class Meta:
        model = DriverAdvance
        fields = ["driver", "category", "amount", "description"]


class DriverAdvanceFormCreate(forms.ModelForm):
    driver = forms.ModelChoiceField(
        queryset=Driver.objects.all(),
        label="Chofer",
        widget=forms.Select(attrs={"class": "form-select"}),  # ⬅️ CAMBIO: ya no es HiddenInput
        required=True
    )

    category = forms.ChoiceField(
        choices=DriverAdvance.AdvanceCategory.choices,
        label="Categoría",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    amount = forms.DecimalField(
        label="Monto",
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej. 5000.00"})
    )

    description = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Opcional"})
    )

    class Meta:
        model = DriverAdvance
        fields = ["driver", "category", "amount", "description"]


class DriverAddressForm(forms.ModelForm):
    address = forms.CharField(
        label="Dirección",
        max_length=255,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Av. Siempre Viva 742", "class": "form-control"})
    )
    locality = forms.CharField(
        label="Localidad",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Ej. Córdoba", "class": "form-control"})
    )
    postal_code = forms.CharField(
        label="Código Postal",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "Ej. X5000", "class": "form-control"})
    )

    class Meta:
        model = DriverAddress
        fields = ["address", "locality", "postal_code"]

class VehicleInlineForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "description", "driver", "image", "price_per_km"]



class DriverWithVehicleForm(forms.ModelForm):
    plate = forms.CharField(label="Patente del Vehículo", required=False)
    description = forms.CharField(label="Descripción del Vehículo", required=False)

    class Meta:
        model = Driver
        fields = ["name", "surname", "dni", "gmail", "phone", "license_number", "license_expiry"]

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

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'price_per_kilo', 'volume', 'trailer_category', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

DriverAddressFormSet = modelformset_factory(
    DriverAddress,
    form=DriverAddressForm,
    extra=1,
    can_delete=True
)

DriverAdvanceFormSet = modelformset_factory(
    DriverAdvance,
    form=DriverAdvanceForm,
    extra=1,
    can_delete=True
)