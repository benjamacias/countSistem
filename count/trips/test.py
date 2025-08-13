from django.test import TestCase

# Create your tests here.
from .models import Client


class ClientModelTest(TestCase):
    def test_str_representation(self):
        client = Client.objects.create(nombre="juan", apellido="jorge")
        self.assertEqual(str(client), "Juan Jorge")
