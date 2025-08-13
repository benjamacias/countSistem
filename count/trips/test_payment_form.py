from django.test import TestCase
from unittest.mock import patch

from .forms import PaymentForm
from .models import Client, Payment, BillingError


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
