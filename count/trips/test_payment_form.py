from django.test import TestCase
from unittest.mock import patch
from django.urls import reverse
from django.contrib.auth.models import User

from .forms import PaymentForm
from .models import (
    Client,
    Payment,
    BillingError,
    Driver,
    Vehicle,
    Product,
    Trip,
    Invoice,
)



class PaymentFormBillingErrorTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(nombre="Tester")

    def test_payment_saved_before_billing_error(self):
        data = {
            "client": self.client_obj.id,
            "tipo_cbte": 6,
            "punto_venta": 1,
            "generar_factura": True,
            "method": "tarjeta",
            "amount": "100.00",
        }
        form = PaymentForm(data)
        self.assertTrue(form.is_valid())
        with patch("trips.forms.emitir_factura_dinamica", side_effect=Exception("fail")):
            form.save()
        payment = Payment.objects.first()
        self.assertIsNotNone(payment)
        error = BillingError.objects.first()
        self.assertIsNotNone(error)
        self.assertEqual(error.payment, payment)
        self.assertTrue(hasattr(form, "billing_error_message"))

class PaymentCreateViewBillingErrorMessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.login(username="u", password="p")

        self.client_obj = Client.objects.create(nombre="Tester")
        self.driver = Driver.objects.create(name="D")
        self.vehicle = Vehicle.objects.create(plate="ABC123", driver=self.driver)
        self.product = Product.objects.create(
            name="Prod",
            price_per_kilo=1,
            volume=1,
            trailer_category="flatbed",
        )
        self.trip = Trip.objects.create(
            client=self.client_obj,
            driver=self.driver,
            vehicle=self.vehicle,
            product=self.product,
            start_address="A",
            end_address="B",
            total_weight=1,
            value=100,
        )
        self.invoice = Invoice.objects.create(trip=self.trip, amount=100)

    def test_warning_message_displayed_when_billing_fails(self):
        url = reverse("trips:payment_create", args=[self.invoice.id])
        data = {
            "client": self.client_obj.id,
            "tipo_cbte": 6,
            "punto_venta": 1,
            "generar_factura": True,
            "method": "tarjeta",
            "amount": "100.00",
        }
        with patch("trips.forms.emitir_factura_dinamica", side_effect=Exception("fail")):
            response = self.client.post(url, data, follow=True)

        messages_list = list(response.context["messages"])
        self.assertTrue(
            any("ARCA rechazó la factura" in m.message for m in messages_list)
        )
        self.assertEqual(
            response.request["PATH_INFO"],
            reverse("trips:invoice_detail", args=[self.invoice.id]),
        )

