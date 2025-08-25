from django import forms
from django.forms import inlineformset_factory
from .models import Trip, TripAddress, Payment
from .models import Client, Driver, Vehicle, Trailer, Asesoramiento, Invoice, Product, DriverAddress, DriverAdvance, BillingError
import re
from django import forms
from django.core.exceptions import ValidationError
import logging
from django.forms import modelformset_factory
import datetime
from django.db.models import Q
from .fact_arca import emitir_factura_dinamica



emitir_factura_dinamica = None

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
        exclude = ["received_weight"]  
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
            tipo_cbte = int(self.cleaned_data["tipo_cbte"])
            punto_venta = self.cleaned_data["punto_venta"]
            cliente_cuit = int(client.cuit or 0)
            importe_total = float(payment.amount)

            # Mapear tipo_iva textual a ID para AFIP
            COND_IVA_MAP = {
                "RI": 1,
                "MT": 6,
                "CF": 5,
                "EX": 4,
                "NR": 3,
            }
            cliente_condicion_iva = COND_IVA_MAP.get(client.tipo_iva, 5)  # Default a Consumidor Final

            # Emitir factura real con AFIP
            try:
                global emitir_factura_dinamica
                if emitir_factura_dinamica is None:
                    from .fact_arca import emitir_factura_dinamica as ef
                    emitir_factura_dinamica = ef
                result = emitir_factura_dinamica(
                    cliente_cuit=cliente_cuit,
                    condicion_iva_id=cliente_condicion_iva,
                    tipo_cbte=tipo_cbte,
                    imp_total=importe_total,
                    punto_venta=punto_venta,
                )
                print(f"Resultado de emisión: {result}")
                detalle = result.FeDetResp.FECAEDetResponse[0]
                if detalle.Resultado != "A":
                    raise ValidationError("AFIP no aprobó la factura")

                cae = detalle.CAE
                vencimiento_cae = datetime.datetime.strptime(
                    detalle.CAEFchVto, "%Y%m%d"
                ).date()

                # Crear el objeto Invoice
                invoice = Invoice.objects.create(
                    client=trip.client if trip else client,
                    amount=payment.amount,
                    punto_venta=punto_venta,
                    tipo_cbte=tipo_cbte,
                    cae=cae,
                    cae_vencimiento=vencimiento_cae,
                )
                if trip:
                    invoice.trips.add(trip)

                payment.invoice = invoice
                payment.factura_emitida = True  # <- Setea el campo solo si fue aprobada

            except Exception as e:
                if not payment.pk:
                    payment.save()
                BillingError.objects.create(payment=payment, error_message=str(e))
                logger.warning(f"Error al emitir factura: {e}")
                self.billing_error_message = (
                    "ARCA rechazó la factura. Verifique el tipo de "
                    "comprobante y los datos del cliente; se completará más tarde."
                )

        if commit:
            payment.save()
            if payment.invoice:
                logger.info(f"Factura creada: {payment.invoice}")
                if payment.invoice.trips.exists():
                    for trip in payment.invoice.trips.all():
                        logger.info(f"Estado del viaje: {trip.status}")

        return payment


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
        widgets = {
            "plate": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: ABC123"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "driver": forms.Select(attrs={"class": "form-select"}),
            "image": forms.FileInput(attrs={"class": "form-control"}),
            "price_per_km": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }

    def clean_plate(self):
        plate = self.cleaned_data.get("plate", "").upper().replace(" ", "")
        pattern1 = r'^[A-Z]{3}\d{3}$'         # ABC123
        pattern2 = r'^\d{2}[A-Z]{3}\d{2}$'    # 12ABC34

        if not re.fullmatch(pattern1, plate) and not re.fullmatch(pattern2, plate):
            raise ValidationError("Formato de patente inválido. Use XXX000 o 00XXX00.")

        # Verificación de unicidad (excluyendo el vehículo actual en edición)
        existing = Vehicle.objects.filter(plate=plate)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError("Esa patente ya está registrada.")

        return plate


class TrailerForm(forms.ModelForm):
    class Meta:
        model = Trailer
        fields = [
            "license_plate",
            "license_expiry",
            "technical_id",
            "technical_expiry",
            "cargo_type",
            "homologation",
            "image",
        ]
        widgets = {
            "license_plate": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Ej: ABC123"}
            ),
            "license_expiry": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "technical_id": forms.TextInput(attrs={"class": "form-control"}),
            "technical_expiry": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}
            ),
            "cargo_type": forms.TextInput(attrs={"class": "form-control"}),
            "homologation": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "image": forms.FileInput(attrs={"class": "form-control"}),
        }

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
            "license_front_image",
            "license_back_image",
            "insurance_policy_pdf",
            "technical_doc_pdf",
        ]
        widgets = {
            "license_expiry": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "license_front_image": forms.FileInput(attrs={"class": "form-control"}),
            "license_back_image": forms.FileInput(attrs={"class": "form-control"}),
            "insurance_policy_pdf": forms.FileInput(attrs={"class": "form-control", "accept": "application/pdf"}),
            "technical_doc_pdf": forms.FileInput(attrs={"class": "form-control", "accept": "application/pdf"}),
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
        choices=[("", "---------")] + list(DriverAdvance.AdvanceCategory.choices),
        label="Categoría",
        widget=forms.Select(attrs={"class": "form-select"}),
        required=False,
    )

    amount = forms.DecimalField(
        label="Monto",
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Ej. 5000.00"}),
        required=False,
    )

    description = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Opcional"})
    )

    class Meta:
        model = DriverAdvance
        fields = ["driver", "category", "amount", "description"]

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        amount = cleaned_data.get("amount")
        description = cleaned_data.get("description")

        if category or amount or description:
            if not category:
                self.add_error("category", "Este campo es obligatorio.")
            if not amount:
                self.add_error("amount", "Este campo es obligatorio.")

        return cleaned_data


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


class CartaPorteForm(forms.Form):
    invoice = forms.ModelChoiceField(queryset=Invoice.objects.none(), label="Factura")
    ctg = forms.CharField(label="Número CTG")

    def __init__(self, *args, client=None, **kwargs):
        super().__init__(*args, **kwargs)
        if client:
            self.fields["invoice"].queryset = (
                Invoice.objects.filter(
                    Q(trips__client=client) | Q(trips__isnull=True)
                ).distinct()
            )


class CartaPorteClientForm(forms.Form):
    client = forms.ModelChoiceField(queryset=Client.objects.all(), label="Cliente")

