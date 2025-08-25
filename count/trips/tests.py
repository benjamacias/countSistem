from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
import io
from contextlib import redirect_stdout

from trips.models import (
    validate_plate,
    Client,
    Driver,
    Vehicle,
    Product,
    Trip,
    Trailer,
)

class ValidatePlateTests(TestCase):
    def test_accepts_valid_formats(self):
        try:
            validate_plate("ABC123")
            validate_plate("12ABC34")
        except ValidationError:
            self.fail("validate_plate raised ValidationError for a valid plate")

    def test_rejects_invalid_format(self):
        with self.assertRaises(ValidationError):
            validate_plate("AB1234")

    def test_rejects_lowercase_and_extra_chars(self):
        for plate in ["abc123", "ABC1234", "A1B2C3"]:
            with self.assertRaises(ValidationError):
                validate_plate(plate)


class TripCleanTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(nombre="test")
        self.driver = Driver.objects.create(name="Driver")
        self.vehicle = Vehicle.objects.create(plate="AAA111")
        self.product = Product.objects.create(
            name="Prod",
            price_per_kilo=Decimal("1"),
            volume=Decimal("1"),
            trailer_category=Product.TrailerType.FLATBED,
        )

    def test_invalid_arrival_date(self):
        trip = Trip(
            client=self.client_obj,
            driver=self.driver,
            vehicle=self.vehicle,
            product=self.product,
            start_address="A",
            end_address="B",
            value=Decimal("10"),
            departure_date=timezone.now(),
            arrival_date=timezone.now() - timezone.timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            trip.clean()

    def test_negative_or_excess_received_weight(self):
        base_kwargs = dict(
            client=self.client_obj,
            driver=self.driver,
            vehicle=self.vehicle,
            product=self.product,
            start_address="A",
            end_address="B",
            value=Decimal("10"),
            departure_date=timezone.now(),
            arrival_date=timezone.now() + timezone.timedelta(days=1),
            total_weight=Decimal("100"),
        )
        trip = Trip(received_weight=Decimal("-1"), **base_kwargs)
        with self.assertRaises(ValidationError):
            trip.clean()

        trip = Trip(received_weight=Decimal("150"), **base_kwargs)
        with self.assertRaises(ValidationError):
            trip.clean()

    def test_delivered_weight_property(self):
        trip = Trip(
            client=self.client_obj,
            driver=self.driver,
            vehicle=self.vehicle,
            product=self.product,
            start_address="A",
            end_address="B",
            value=Decimal("10"),
            total_weight=Decimal("100"),
            received_weight=Decimal("40"),
        )
        self.assertEqual(trip.delivered_weight, Decimal("60"))


class VehicleListPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        for i in range(8):
            Vehicle.objects.create(plate=f"BBB{i:03d}")

    def test_pagination(self):
        self.client.force_login(self.user)
        url = reverse("trips:vehicles_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 6)
        response = self.client.get(url + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["page_obj"].object_list), 2)

    def test_custom_page_size_ignored_if_invalid(self):
        self.client.force_login(self.user)
        url = reverse("trips:vehicles_list")
        # limit parameter is ignored due to view logic so page size remains 6
        response = self.client.get(url + "?limit=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 6)


class TrailerHomologationTests(TestCase):
    def test_homologation_set_false_when_license_expired(self):
        expired_date = timezone.now().date() - timezone.timedelta(days=1)
        trailer = Trailer.objects.create(
            license_plate="AAA123",
            license_expiry=expired_date,
            technical_id="TECH1",
            technical_expiry=expired_date,
            cargo_type="Granos",
            homologation=True,
        )
        trailer.refresh_from_db()
        self.assertFalse(trailer.homologation)

    def test_homologation_remains_true_with_valid_license(self):
        future_date = timezone.now().date() + timezone.timedelta(days=1)
        trailer = Trailer.objects.create(
            license_plate="BBB123",
            license_expiry=future_date,
            technical_id="TECH2",
            technical_expiry=future_date,
            cargo_type="Granos",
            homologation=True,
        )
        trailer.refresh_from_db()
        self.assertTrue(trailer.homologation)


class TrailerViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")

    def test_create_trailer_with_image(self):
        self.client.force_login(self.user)
        url = reverse("trips:trailer_create")
        image_bytes = (
            b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
            b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
            b"\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;"
        )
        image = SimpleUploadedFile("test.gif", image_bytes, content_type="image/gif")
        today = timezone.now().date().isoformat()
        data = {
            "license_plate": "ABC123",
            "license_expiry": today,
            "technical_id": "TECH1",
            "technical_expiry": today,
            "cargo_type": "Granos",
            "homologation": "on",
            "image": image,
        }
        response = self.client.post(url, data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Trailer.objects.count(), 1)


class DriverCreateViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")

    def _formset_data(self, prefix):
        return {
            f"{prefix}-TOTAL_FORMS": "0",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }

    def test_can_create_driver(self):
        self.client.force_login(self.user)
        url = reverse("trips:driver_create")
        data = {
            "name": "John",
            **self._formset_data("addresses"),
            **self._formset_data("advances"),
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Driver.objects.filter(name="John").exists())

    def test_invalid_driver_prints_errors(self):
        self.client.force_login(self.user)
        url = reverse("trips:driver_create")
        data = {
            "name": "",  # Invalid - required
            **self._formset_data("addresses"),
            **self._formset_data("advances"),
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        output = buf.getvalue()
        self.assertIn("Errores en formulario de conductor", output)


