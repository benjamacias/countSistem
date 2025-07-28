from django.test import TestCase

from .models import Client


class ClientModelTest(TestCase):
    def test_str_representation(self):
        client = Client.objects.create(nombre="John", apellido="Doe")
        self.assertEqual(str(client), "John Doe")

