from django.test import SimpleTestCase
from unittest.mock import patch, ANY
from trips.fact_arca import obtener_carta_porte, WSDL_CGT
import base64


class CartaPorteTests(SimpleTestCase):
    def test_obtener_carta_porte_parses_response(self):
        sample = {
            "estado": "vigente",
            "origen": "Buenos Aires",
            "destino": "Córdoba",
            "patente": "ABC123",
            "pdf": base64.b64encode(b"fake-pdf").decode(),
        }

        with patch("trips.fact_arca.Client") as mock_client, \
             patch("trips.fact_arca.obtener_token_sign_desde_cache", return_value=("tok", "sig")):
            mock_client.return_value.service.consultarCTG.return_value = sample

            resp = obtener_carta_porte(123)

            mock_client.assert_called_once_with(WSDL_CGT, transport=ANY)
            mock_client.return_value.service.consultarCTG.assert_called_once()
            self.assertEqual(
                resp,
                {
                    "estado": "vigente",
                    "origen": "Buenos Aires",
                    "destino": "Córdoba",
                    "patente": "ABC123",
                    "pdf": b"fake-pdf",
                },
            )
