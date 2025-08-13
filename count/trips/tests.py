from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User

from trips.models import (
    validate_plate,
    Client,
    Driver,
    Vehicle,
    Product,
    Trip,
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

