from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import re
from django.db.models import Sum
from django.db import models

def validate_plate(value):
    pattern1 = r'^[A-Z]{3}\d{3}$'      # Ej: ABC123
    pattern2 = r'^\d{2}[A-Z]{3}\d{2}$' # Ej: 12ABC34
    if not re.match(pattern1, value) and not re.match(pattern2, value):
        raise ValidationError("Formato de patente inválido. Use XXX000 o 00XXX00.")


class Client(models.Model):
    nombre = models.CharField(max_length=100, blank=True)
    apellido = models.CharField(max_length=100, blank=True)
    domicilio = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    dni = models.CharField(max_length=20, unique=True, blank=True, null=True)
    gmail = models.EmailField(max_length=254, unique=True, blank=True, null=True)

    # Nuevos campos AFIP
    cuit = models.CharField(max_length=11, blank=True, null=True, unique=True)
    tipo_iva = models.CharField(
        max_length=20,
        choices=[
            ("RI", "Responsable Inscripto"),
            ("MT", "Monotributista"),
            ("CF", "Consumidor Final"),
            ("EX", "Exento"),
            ("NR", "No Responsable"),
        ],
        default="CF"
    )

    def __str__(self):
        nombre = (self.nombre or "").strip().title()
        apellido = (self.apellido or "").strip().title()
        return f"{nombre} {apellido}".strip()
        
    @property
    def total_facturado(self):
        return (
            Invoice.objects.filter(client=self)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

    @property
    def total_pagado(self):
        return (
            Payment.objects.filter(invoice__client=self)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

    @property
    def total_restante(self):
        return self.total_facturado - self.total_pagado


class Asesoramiento(models.Model):
    cliente = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='asesoramientos')
    tipo = models.CharField(max_length=100)
    asesoramiento = models.TextField()

    def __str__(self):
        return f"Asesoramiento de {self.cliente}"

class Product(models.Model):
    class TrailerType(models.TextChoices):
        FLATBED = "flatbed", "Remolque de plataforma (Flatbed)"
        DRY_VAN = "dry_van", "Remolque cerrado (Dry Van)"
        REEFER = "reefer", "Remolque refrigerado (Reefer)"
        TANKER = "tanker", "Remolque cisterna (Tanker)"
        TAUTLINER = "tautliner", "Remolque de lona (Tautliner)"
        CHASSIS = "chassis", "Remolque portacontenedores (Chassis)"
        LOWBOY = "lowboy", "Remolque Lowboy (Cama baja)"
        HOPPER = "hopper", "Remolque tolva (Hopper)"
        LIVESTOCK = "livestock", "Remolque jaula (Livestock trailer)"
        CAR_CARRIER = "car_carrier", "Remolque de automóviles (Car carrier)"
        DUMP_TRAILER = "dump_trailer", "Remolque basculante (Dump trailer)"

    name = models.CharField("Nombre", max_length=100)
    price_per_kilo = models.DecimalField("Precio por kilo", max_digits=10, decimal_places=2)
    volume = models.DecimalField("Volumen (m³)", max_digits=10, decimal_places=2)
    trailer_category = models.CharField(
        "Tipo de remolque necesario",
        max_length=20,
        choices=TrailerType.choices
    )
    description = models.TextField("Descripción", blank=True)

    def __str__(self):
        return self.name
    
    @property
    def trailer_category_display(self):
        return self.get_trailer_category_display()
    

class Driver(models.Model):
    name = models.CharField(max_length=120)
    surname = models.CharField(max_length=120, blank=True, null=True)
    dni = models.CharField(max_length=20, unique=True, blank=True, null=True, help_text="DNI del conductor")
    gmail = models.EmailField(max_length=254, unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    license_number = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Número de licencia del conductor")
    license_expiry = models.DateField("Vencimiento de licencia", blank=True, null=True)
    license_front_image = models.ImageField(upload_to="drivers/licenses/", null=True, blank=True)
    license_back_image = models.ImageField(upload_to="drivers/licenses/", null=True, blank=True)
    insurance_policy_pdf = models.FileField(upload_to="drivers/policy/", null=True, blank=True)
    technical_doc_pdf = models.FileField(upload_to="drivers/technical/", null=True, blank=True)

    def __str__(self):
        return f"{self.name} {self.surname or ''}"

class DriverAddress(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="addresses")
    address = models.CharField("Dirección", max_length=255)
    locality = models.CharField("Localidad", max_length=100)
    postal_code = models.CharField("Código Postal", max_length=20)

    def __str__(self):
        return f"{self.address}, {self.locality}"
        
class DriverAdvance(models.Model):
    class AdvanceCategory(models.TextChoices):
        TOLL = "peaje", "Peaje"
        FUEL = "combustible", "Combustible"
        OTHER = "otro", "Otro"

    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name="advances")
    category = models.CharField("Categoría", max_length=20, choices=AdvanceCategory.choices)
    amount = models.DecimalField("Monto", max_digits=10, decimal_places=2)
    date = models.DateField("Fecha", auto_now_add=True)
    description = models.TextField("Descripción", blank=True)

    def __str__(self):
        return f"{self.get_category_display()} - ${self.amount} ({self.date})"


class Vehicle(models.Model):
    plate = models.CharField("Patente", max_length=15, unique=True, validators=[validate_plate])
    description = models.CharField(max_length=120, blank=True)
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True)
    image = models.ImageField(upload_to="vehicles/", null=True, blank=True)
    price_per_km = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Precio por kilómetro del vehículo")
    def __str__(self):
        return self.plate


class Trailer(models.Model):
    license_plate = models.CharField(
        "Licencia",
        max_length=15,
        unique=True,
        validators=[validate_plate],
    )
    license_expiry = models.DateField("Vencimiento de licencia")
    technical_id = models.CharField("Técnica", max_length=100)
    technical_expiry = models.DateField("Vencimiento de técnica")
    cargo_type = models.CharField("Tipo de carga", max_length=100)
    homologation = models.BooleanField("Homologación", default=False)

    def save(self, *args, **kwargs):
        from django.utils import timezone

        if self.license_expiry and self.license_expiry < timezone.now().date():
            self.homologation = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.license_plate


class Trip(models.Model):

    STATUS_CHOICES = [
        ("pendiente", "Pendiente"),
        ("recibido", "Recibido"),
        ("facturado", "Facturado"),
        ("no_completado", "No completado"),
        ('cancelado', 'Cancelado'),  
    ]
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    start_address = models.CharField(max_length=255)
    end_address = models.CharField(max_length=255)
    total_weight = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    value = models.DecimalField("Valor del viaje", max_digits=12, decimal_places=2)
    received_weight = models.DecimalField("Kilos recibidos", max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="pendiente")

    departure_date = models.DateTimeField(null=True, blank=True)  # Fecha de salida
    arrival_date = models.DateTimeField(null=True, blank=True)    # Fecha de llegada

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Viaje #{self.id} - {self.client}"
    
    def clean(self):
        if self.arrival_date and self.arrival_date < self.departure_date:
            raise ValidationError("La fecha de llegada no puede ser antes de la fecha de salida.")
        if self.received_weight < 0:
            raise ValidationError("Los kilos recibidos no pueden ser negativos.")
        if self.received_weight > self.total_weight:
            raise ValidationError("Los kilos recibidos no pueden ser mayores al peso total.")
    
    @property
    def delivered_weight(self):
        return self.total_weight - self.received_weight


class TripAddress(models.Model):
    trip = models.ForeignKey(Trip, related_name="addresses", on_delete=models.CASCADE)
    address = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)


    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.address

class Invoice(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invoices")
    trips = models.ManyToManyField(Trip, related_name="invoices", blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    # Nuevos campos AFIP
    punto_venta = models.PositiveIntegerField(default=1)
    tipo_cbte = models.PositiveIntegerField(default=6)
    cae = models.CharField(max_length=14, blank=True, null=True)
    cae_vencimiento = models.DateField(blank=True, null=True)
    carta_porte_ctg = models.CharField(max_length=20, blank=True, null=True)
    carta_porte_pdf = models.BinaryField(blank=True, null=True)

    def paid_total(self):
        return sum(p.amount for p in self.payments.all())

    def payment_count(self):
        return self.payments.count()
    
    def remaining(self):
        return self.amount - self.paid_total()

    def __str__(self):
        return f"Factura #{self.id}"

class Payment(models.Model):
    METHOD_CHOICES = [
        ("nota_credito", "Nota de crédito"),
        ("tarjeta", "Tarjeta"),
        ("transferencia", "Transferencia"),
        ("efectivo", "Efectivo"),
        ("cheque", "Cheque"),
        ("retencion", "Retención"),
        ("otro", "Otro"),
    ]

    invoice = models.ForeignKey(Invoice, related_name="payments", on_delete=models.CASCADE, null=True, blank=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    factura_emitida = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.method} - ${self.amount}"


class BillingError(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="billing_errors")
    error_message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    fixed = models.BooleanField(default=False)

    def __str__(self):
        return f"Error de facturación #{self.id}"

