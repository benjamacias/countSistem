from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from unittest.mock import patch
from django.core import mail

from .models import Client, Driver, Vehicle, Product, Trip, Invoice


class CartaPorteViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.login(username="u", password="p")
        self.client_obj = Client.objects.create(nombre="Tester", gmail="t@test.com")
        self.driver = Driver.objects.create(name="D")
        self.vehicle = Vehicle.objects.create(plate="ABC123", driver=self.driver)
        self.product = Product.objects.create(
            name="Prod", price_per_kilo=1, volume=1, trailer_category="flatbed"
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
        self.invoice = Invoice.objects.create(amount=100)
        self.invoice.trips.add(self.trip)
        self.invoice_no_trip = Invoice.objects.create(amount=50)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    @patch('trips.views.obtener_carta_porte')
    def test_links_invoice_and_sends_mail(self, mock_obtener):
        mock_obtener.return_value = {
            "estado": "v", "origen": "o", "destino": "d", "patente": "p", "pdf": b"pdf"
        }
        url = reverse('trips:carta_porte_invoice', args=[self.client_obj.id])
        data = {"invoice": self.invoice.id, "ctg": "123"}
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('trips:invoice_detail', args=[self.invoice.id]))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.carta_porte_ctg, "123")
        self.assertEqual(self.invoice.carta_porte_pdf, b"pdf")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].attachments)

    def test_start_view_redirects_to_client(self):
        url = reverse('trips:carta_porte_start')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, {'client': self.client_obj.id})
        self.assertRedirects(response, reverse('trips:carta_porte_invoice', args=[self.client_obj.id]))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    @patch('trips.views.obtener_carta_porte')
    def test_creates_trip_from_carta_porte(self, mock_obtener):
        mock_obtener.return_value = {
            "estado": "v", "origen": "o", "destino": "d", "patente": "ABC123", "pdf": b"pdf"
        }
        url = reverse('trips:carta_porte_invoice', args=[self.client_obj.id])
        data = {"invoice": self.invoice_no_trip.id, "ctg": "123", "action": "create_trip"}
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('trips:invoice_detail', args=[self.invoice_no_trip.id]))
        self.invoice_no_trip.refresh_from_db()
        trip = self.invoice_no_trip.trips.first()
        self.assertIsNotNone(trip)
        self.assertEqual(trip.start_address, "o")
        self.assertEqual(trip.end_address, "d")
        self.assertEqual(trip.status, "recibido")
        self.assertEqual(trip.vehicle, self.vehicle)
        self.assertEqual(trip.driver, self.driver)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].attachments)

